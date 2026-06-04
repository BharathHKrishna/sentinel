"""
Fine-tune MobileNetV3-small for construction change detection.

Expected dataset layout:
  ml/data/construction/
    train/
      positive/   # image patches showing construction change
      negative/   # image patches with no change
    val/
      positive/
      negative/

Each patch is an RGB PNG (before-after difference or after-only composite).
"""
import argparse
import os
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
    print("wandb not installed — logging to stdout only")


DATA_ROOT = Path("ml/data/construction")
MODEL_DIR = Path("models")
CLASS = "construction"


def get_transforms(train: bool) -> transforms.Compose:
    if train:
        return transforms.Compose([
            transforms.Resize((128, 128)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
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
    last = existing[-1].stem  # e.g. "construction_v3"
    return int(last.split("_v")[-1]) + 1


def train(
    epochs: int = 20,
    batch_size: int = 32,
    lr: float = 1e-3,
    device: str = "auto",
) -> Path:
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")

    if not (DATA_ROOT / "train").exists():
        print(f"ERROR: training data not found at {DATA_ROOT}/train")
        print("Create directories: ml/data/construction/train/positive and /negative")
        sys.exit(1)

    train_dataset = datasets.ImageFolder(DATA_ROOT / "train", transform=get_transforms(train=True))
    val_dataset = datasets.ImageFolder(DATA_ROOT / "val", transform=get_transforms(train=False))

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=4)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=4)

    model = build_model(num_classes=2).to(device)

    # Class weights to handle imbalanced data
    class_counts = torch.tensor([
        len(list((DATA_ROOT / "train" / "negative").glob("*"))),
        len(list((DATA_ROOT / "train" / "positive").glob("*"))),
    ], dtype=torch.float)
    weights = (class_counts.sum() / (2 * class_counts)).to(device)
    criterion = nn.CrossEntropyLoss(weight=weights)

    optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    version = next_version()
    save_path = MODEL_DIR / f"{CLASS}_v{version}.pt"

    if WANDB_AVAILABLE:
        wandb.init(project="sentinel", name=f"{CLASS}-v{version}", config={
            "epochs": epochs, "batch_size": batch_size, "lr": lr, "device": device,
        })

    best_val_acc = 0.0

    for epoch in range(1, epochs + 1):
        # Train
        model.train()
        train_loss, train_correct, train_total = 0.0, 0, 0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * images.size(0)
            preds = outputs.argmax(dim=1)
            train_correct += (preds == labels).sum().item()
            train_total += images.size(0)

        train_loss /= train_total
        train_acc = train_correct / train_total

        # Validate
        model.eval()
        val_loss, val_correct, val_total = 0.0, 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * images.size(0)
                preds = outputs.argmax(dim=1)
                val_correct += (preds == labels).sum().item()
                val_total += images.size(0)

        val_loss /= val_total
        val_acc = val_correct / val_total
        scheduler.step()

        print(
            f"Epoch {epoch:3d}/{epochs} | "
            f"train_loss={train_loss:.4f} train_acc={train_acc:.3f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.3f}"
        )

        if WANDB_AVAILABLE:
            wandb.log({
                "epoch": epoch,
                "train/loss": train_loss,
                "train/acc": train_acc,
                "val/loss": val_loss,
                "val/acc": val_acc,
            })

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), save_path)
            print(f"  → Saved best model (val_acc={val_acc:.4f}) to {save_path}")

    if WANDB_AVAILABLE:
        wandb.finish()

    print(f"\nTraining complete. Best val_acc={best_val_acc:.4f}. Model saved to {save_path}")
    return save_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train construction change detector")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--device", type=str, default="auto")
    args = parser.parse_args()

    train(epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, device=args.device)
