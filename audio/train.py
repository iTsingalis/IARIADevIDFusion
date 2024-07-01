import torch
from tqdm import tqdm


def pred_labels(model, inputs):
    model.eval()
    with torch.no_grad():
        model_outputs = model(inputs)
        _, pred_label = torch.max(model_outputs, dim=1)
    model.train()
    return pred_label


def training(model, device, data_loader, optimizer, loss_fn):
    model.train()
    train_loss, total_acc, total_cnt = 0, 0, 0

    pbar = tqdm(data_loader, disable=False)
    for data in pbar:
        pbar.set_description("Training batch")
        inputs = data[0].to(device)  # [batch, 3, 128, 1500]
        target = data[1].squeeze(1).to(device)  # ([1, ...,]), shape: [batch]

        def closure(backward=True):
            if backward:
                optimizer.zero_grad()
            model_outputs = model(inputs)
            cri_loss = loss_fn(model_outputs, target)

            create_graph = type(optimizer).__name__ == "AdaCubic" or type(
                optimizer).__name__ == "AdaHessian"
            if backward:
                cri_loss.backward(create_graph=create_graph)
            return cri_loss

        loss = optimizer.step(closure=closure)

        train_loss += loss.item()

        pred_label = pred_labels(model, inputs)

        acc = torch.sum((pred_label == target).float()).item()
        total_acc += acc
        total_cnt += target.size(0)

    return train_loss / len(data_loader), total_acc / total_cnt


def validating(model, device, test_loader, loss_fn):
    train_loss, total_acc, total_cnt = 0, 0, 0
    model.eval()
    with torch.no_grad():
        for data in test_loader:
            inputs = data[0].to(device)
            target = data[1].squeeze(1).to(device)

            outputs = model(inputs)
            loss = loss_fn(outputs, target)
            train_loss += loss.item()

            _, pred_label = torch.max(outputs.data, 1)
            total_acc += torch.sum((pred_label == target).float()).item()
            total_cnt += target.size(0)

    return train_loss / len(test_loader), total_acc / total_cnt
