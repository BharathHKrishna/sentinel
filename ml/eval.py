"""
Evaluate a saved Sentinel model on a held-out test split.

Usage:
  python ml/eval.py --model models/solar_v1.pt --class solar
  python ml/eval.py --model models/construction_v2.pt --class construction
"""
import argparse
import sys
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models


def get_transforms() -> transforms.Compose:
    return transforms.Compose([
        transforms.Resize((128, 128)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])


def build_model(num_classes: int = 2) -> nn.Module:
    model = models.mobilenet_v3_small(weights=None)
    in_features = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(in_features, num_classes)
    return model


def evaluate(model_path: str, class_name: str, batch_size: int = 32) -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    test_dir = Path(f"ml/data/{class_name}/test")

    if not test_dir.exists():
        # Fall back to val split
        test_dir = Path(f"ml/data/{class_name}/val")
        if not test_dir.exists():
            print(f"ERROR: No test or val data found at ml/data/{class_name}/test (or /val)")
            sys.exit(1)
        print(f"Note: using val split as test set (no test/ dir found)")

    print(f"Loading model from {model_path}")
    model = build_model()
    state = torch.load(model_path, map_location=device)
    model.load_state_dict(state)
    model.to(device)
    model.eval()

    dataset = datasets.ImageFolder(test_dir, transform=get_transforms())
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=False, num_workers=2)

    class_names = dataset.classes  # e.g. ['negative', 'positive']
    print(f"Classes: {class_names} | Total samples: {len(dataset)}")

    all_labels: list[int] = []
    all_preds: list[int] = []
    all_probs: list[float] = []

    with torch.no_grad():
        for images, labels in loader:
            images = images.to(device)
            outputs = model(images)
            probs = torch.softmax(outputs, dim=1)[:, 1]  # positive class
            preds = outputs.argmax(dim=1)

            all_labels.extend(labels.tolist())
            all_preds.extend(preds.cpu().tolist())
            all_probs.extend(probs.cpu().tolist())

    # Compute metrics
    import numpy as np

    labels_arr = np.array(all_labels)
    preds_arr = np.array(all_preds)

    # Binary: positive class = 1 (index of "positive" folder)
    pos_idx = class_names.index("positive") if "positive" in class_names else 1

    tp = int(((preds_arr == pos_idx) & (labels_arr == pos_idx)).sum())
    fp = int(((preds_arr == pos_idx) & (labels_arr != pos_idx)).sum())
    fn = int(((preds_arr != pos_idx) & (labels_arr == pos_idx)).sum())
    tn = int(((preds_arr != pos_idx) & (labels_arr != pos_idx)).sum())

    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-9)
    accuracy = (tp + tn) / max(len(labels_arr), 1)

    # AUC-ROC
    try:
        from sklearn.metrics import roc_auc_score, confusion_matrix  # type: ignore
        auc = roc_auc_score(labels_arr == pos_idx, np.array(all_probs))
        auc_str = f"{auc:.4f}"
    except ImportError:
        auc_str = "N/A (install scikit-learn)"

    print("\n" + "=" * 50)
    print(f"Evaluation Results — {class_name} detector")
    print("=" * 50)
    print(f"  Accuracy   : {accuracy:.4f}  ({tp + tn}/{len(labels_arr)})")
    print(f"  Precision  : {precision:.4f}")
    print(f"  Recall     : {recall:.4f}")
    print(f"  F1 Score   : {f1:.4f}")
    print(f"  AUC-ROC    : {auc_str}")
    print(f"\n  Confusion Matrix (rows=actual, cols=predicted):")
    print(f"               Neg    Pos")
    print(f"  Actual Neg:  {tn:5d}  {fp:5d}")
    print(f"  Actual Pos:  {fn:5d}  {tp:5d}")
    print("=" * 50)

    # Per-class breakdown
    for idx, cname in enumerate(class_names):
        n = int((labels_arr == idx).sum())
        correct = int(((preds_arr == idx) & (labels_arr == idx)).sum())
        print(f"  Class '{cname}': {correct}/{n} correct ({100*correct/max(n,1):.1f}%)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate a Sentinel model")
    parser.add_argument("--model", required=True, help="Path to .pt model file")
    parser.add_argument("--class", dest="class_name", required=True,
                        choices=["construction", "solar", "fire", "flood", "deforestation"],
                        help="Detection class name")
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args()

    evaluate(args.model, args.class_name, args.batch_size)
