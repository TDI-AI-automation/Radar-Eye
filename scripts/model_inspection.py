import torch

ckpt = torch.load(
    "models/yolo26m_weapon.pt",
    map_location="cpu"
)

print("TOP LEVEL KEYS")
print("=" * 80)

for k in ckpt.keys():
    print(k)

print("\nTRAIN_ARGS")
print("=" * 80)

train_args = ckpt.get("train_args")

if train_args:
    for k, v in train_args.items():
        print(f"{k}: {v}")

print("\nMODEL INFO")
print("=" * 80)

model = ckpt.get("model")

print(type(model))

if hasattr(model, "names"):
    print("\nCLASSES")
    print(model.names)

if hasattr(model, "nc"):
    print("\nNUM_CLASSES")
    print(model.nc)