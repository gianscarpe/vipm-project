import torch
from torch import optim
import torch.nn.functional as F
from torchvision import transforms
from matcher.models import TwoPhaseNet
from matcher.dataset import ClassificationDataset
from torch.utils.data import DataLoader
from torch.nn import CrossEntropyLoss
import time
import os
import numpy as np


def main():
    config = {
        "phase": "2",
        "save_every_freq": False,
        "save_frequency": 2,
        "save_best": True,
        "classes": ["subCategory"],  # subCategory masterCategory
        "model_name": "resnet18",
        "batch_size": 16,
        "lr": 0.0001,
        "num_epochs": 30,
        "weight_decay": 0.0001,
        "exp_base_dir": "data/exps/",
        "image_size": [224, 224],
        "load_path": None,
    }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    start_epoch = 1
    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]
    )

    train_dataset = ClassificationDataset(
        "./data/images/",
        "./data/small_train.csv",
        distinguish_class=config["classes"],
        load_path=None,
        image_size=config["image_size"],
        transform=normalize,
    )
    train_loader = DataLoader(
        train_dataset, batch_size=config["batch_size"], shuffle=True
    )
    val_loader = DataLoader(
        ClassificationDataset(
            "./data/images",
            "./data/small_val.csv",
            distinguish_class=config["classes"],
            image_size=config["image_size"],
            transform=normalize,
            label_encoder=train_dataset.les,
        ),
        batch_size=config["batch_size"],
        shuffle=True,
    )
    if config["phase"] == "1":
        model = TwoPhaseNet(
            image_size=config["image_size"],
            n_classes_phase1=6,
            n_classes_phase2=43,
            name=config["model_name"],
        )
        model.phase1()
    elif config["phase"] == "2":
        model = TwoPhaseNet(
            image_size=config["image_size"],
            n_classes_phase1=6,
            n_classes_phase2=43,
            name=config["model_name"],
        )
        pretrained_dict = torch.load("data/exps/resnet18_phase1_best.pt")
        model_dict = model.state_dict()
        pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict}
        model_dict.update(pretrained_dict)
        model.load_state_dict(pretrained_dict)
        model.phase2()

    optimizer = optim.Adam(
        model.parameters(), lr=config["lr"], weight_decay=config["weight_decay"]
    )

    best_accu = 0.0
    for epoch in range(start_epoch, config["num_epochs"] + 1):
        train(
            model,
            device,
            train_loader,
            epoch,
            optimizer,
            config["batch_size"],
            n_label=1,
        )
        accuracy = test(model, device, val_loader, n_label=1)
        if config["save_every_freq"]:
            if epoch % config["save_frequency"] == 0:
                torch.save(
                    model.state_dict(),
                    os.path.join(
                        config["exp_base_dir"],
                        config["model_name"] + "_{:03}.pt".format(epoch),
                    ),
                )
        if config["save_best"]:
            if accuracy > best_accu:
                print("* PORCA L'OCA SAVE BEST")
                best_accu = accuracy
                torch.save(
                    model.state_dict(),
                    os.path.join(
                        config["exp_base_dir"],
                        config["model_name"] + "_phase" + config["phase"] + "_best.pt",
                    ),
                )


def train(model, device, train_loader, epoch, optimizer, batch_size, n_label=3):
    model.train()
    model.to(device)
    t0 = time.time()
    training_loss = []
    criterions = [CrossEntropyLoss() for i in range(n_label)]
    for batch_idx, (data, target) in enumerate(train_loader):
        data = data.to(device)
        target = target.long().to(device)

        optimizer.zero_grad()
        output = model(data)
        loss = 0
        for i in range(n_label):
            loss = loss + criterions[i](torch.squeeze(output), target[:, 0])

        loss.backward()
        # loss_items = []
        # for i in range(n_label):
        #     loss_items.append(loss[i].item())
        #     loss[i].backward()

        training_loss.append(loss.item())
        optimizer.step()
        if batch_idx % 10 == 0:
            print(
                "Train Epoch: {} [{}/{} ({:.0f}%)] \tBatch Loss: ({})".format(
                    epoch,
                    batch_idx * batch_size,
                    len(train_loader.dataset),
                    100.0 * batch_idx * batch_size / len(train_loader.dataset),
                    "{:.6f}".format(loss.item()),
                )
            )
    print(
        "Train Epoch: {}\t time:{:.3f}s \tMeanLoss: ({})".format(
            epoch, (time.time() - t0), "{:.6f}".format(np.average(training_loss))
        )
    )


def test(model, device, test_loader, n_label=3):
    model.eval()
    model.to(device)
    with torch.no_grad():
        accurate_labels = 0
        all_labels = 0
        val_loss = 0
        for batch_idx, (data, target) in enumerate(test_loader):
            data = data.to(device)
            target = target.long().to(device)

            output = model(data)
            val_loss = (
                val_loss + F.cross_entropy(torch.squeeze(output), target[:, 0]).item()
            )

            accurate_labels += torch.sum(
                (torch.argmax(F.softmax(output), dim=1) == target[:, 0])
            )

            all_labels += len(target)

        accuracy = 100.0 * accurate_labels.item() / all_labels
        print(
            "Test accuracy: ({})/{} ({}), Loss: ({})".format(
                str(accurate_labels.item()),
                all_labels,
                "{:.3f}%".format(accuracy),
                "{:.6f}".format(val_loss / all_labels),
            )
        )
        return accuracy


if __name__ == "__main__":
    main()
