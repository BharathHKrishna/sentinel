"""
Fine-tune MobileNetV3-small for solar farm detection.

Expected dataset layout:
  ml/data/solar/
    train/
      positive/   # patches containing solar farms
      negative/   # patches with no solar farms
    val/
      positive/
      negative/

Saves model to models/solar_v{version}.pt.
The latest model is also copied to models/solar_current.pt
so the SolarDetector service can load it automatically.
"""
import argparse
import shutil
import sys
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models

try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

DATA_ROOT = Path("ml/data/solar")
MODEL_DIR = Path("models")
CLASS = "solar"


def get_transforms(train: bool) -> transforms.Compose:
    if train:
        return transforms.Compose([
            transforms.Resize((128, 128)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            transforms.RandomRotation(90),
            # Solar panels have distinctive spectral signature — augment brightness carefully
            transforms.ColorJitter(brightness=0.15, contrast=0.15),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])
    return transforms.Compose([
        transforms.Resize((128, 128)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


def build_model(num_classes: int = 2) -> nn.Module:
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.IMAGENET1K_V1)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model


def next_version() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(MODEL_DIR.glob(f"{CLASS}_v*.pt"))
    if not existing:
        return 1
    return int(existing[-1].stem.split("_v")[-1]) + 1


def train(
    epochs: int = 20,
    batch_size: int = 32,
    lr: float = 5e-4,
    device: str = "auto",
) -> Path:
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    if not (DATA_ROOT / "train").exists():
        print(f"ERROR: training data not found at {DATA_ROOT}/train")
        sys.exit(1)

    train_dataset = datasets.ImageFolder(DATA_ROOT / "train", transform=get_transforms(train=True))
    val_dataset = datasets.ImageFolder(DATA_ROOT / "val", transform=get_transforms(train=False))

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=4)

    model = build_model(num_classes=2).to(device)

    # Solar farms are relatively rare → up-weight positive class
    pos_count = len(list((DATA_ROOT / "train" / "positive").glob("*")))
    neg_count = len(list((DATA_ROOT / "train" / "negative").glob("*")))
    total = pos_count + neg_count
    weights = torch.tensor([total / (2 * neg_count), total / (2 * pos_count)], dtype=torch.float).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)

    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=lr * 10, epochs=epochs, steps_per_epoch=len(train_loader)
    )

    version = next_version()
    save_path = MODEL_DIR / f"{CLASS}_v{version}.pt"
    current_path = MODEL_DIR / "solar_current.pt"

    if WANDB_AVAILABLE:
        wandb.init(project="sentinel", name=f"solar-v{version}", config={
            "epochs": epochs, "batch_size": batch_size, "lr": lr,
        })

    best_val_f1 = 0.0

    for epoch in range(1, epochs + 1):
        # Train
        model.train()
        train_loss = 0.0
        train_tp = train_fp = train_fn = train_total = 0

        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            scheduler.step()

            train_loss += loss.item() * images.size(0)
            preds = outputs.argmax(dim=1)
            train_tp += ((preds == 1) & (labels == 1)).sum().item()
            train_fp += ((preds == 1) & (labels == 0)).sum().item()
            train_fn += ((preds == 0) & (labels == 1)).sum().item()
            train_total += images.size(0)

        train_precision = train_tp / max(train_tp + train_fp, 1)
        train_recall = train_tp / max(train_tp + train_fn, 1)
        train_f1 = 2 * train_precision * train_recall / max(train_precision + train_recall, 1e-6)

        # Validate
        model.eval()
        val_loss = 0.0
        val_tp = val_fp = val_fn = val_total = 0

        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * images.size(0)
                preds = outputs.argmax(dim=1)
                val_tp += ((preds == 1) & (labels == 1)).sum().item()
                val_fp += ((preds == 1) & (labels == 0)).sum().item()
                val_fn += ((preds == 0) & (labels == 1)).sum().item()
                val_total += images.size(0)

        val_precision = val_tp / max(val_tp + val_fp, 1)
        val_recall = val_tp / max(val_tp + val_fn, 1)
        val_f1 = 2 * val_precision * val_recall / max(val_precision + val_recall, 1e-6)

        print(
            f"Epoch {epoch:3d}/{epochs} | "
            f"train_f1={train_f1:.3f} | "
            f"val_f1={val_f1:.3f} val_prec={val_precision:.3f} val_rec={val_recall:.3f}"
        )

        if WANDB_AVAILABLE:
            wandb.log({
                "epoch": epoch,
                "train/f1": train_f1,
                "val/f1": val_f1,
                "val/precision": val_precision,
                "val/recall": val_recall,
            })

        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            torch.save(model.state_dict(), save_path)
            # Update the "current" symlink used by the service
            shutil.copy2(save_path, current_path)
            print(f"  → Saved best model (val_f1={val_f1:.4f}) to {save_path}")

    if WANDB_AVAILABLE:
        wandb.finish()

    print(f"\nTraining complete. Best val_F1={best_val_f1:.4f}. Model saved to {save_path}")
    print(f"solar_current.pt updated → {current_path}")
    return save_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train solar farm detector")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=5e-4)
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()

    train(epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, device=args.device)
