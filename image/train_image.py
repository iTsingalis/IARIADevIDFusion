import os
import json
import argparse
import torch
from models.audio_image_models import *
from image.dataset import ImageDataset
from train import training, validating
from torch.utils.data import DataLoader
from tensorboardX import SummaryWriter
# from optimizers.AdaCubic import AdaCubic
from torch.optim.lr_scheduler import MultiStepLR
from utils import save_checkpoint, check_run_folder


def get_args():
    parser = argparse.ArgumentParser()
    # path #
    parser.add_argument("--results_dir", type=str, required=True)
    parser.add_argument("--project_dir", type=str, required=True)
    parser.add_argument("--vision_frames_dir", type=str, required=True)

    # parameter #
    parser.add_argument("--cuda", default=0, type=int, help='Specify cuda number')
    parser.add_argument("--epochs", default=10, type=int)
    parser.add_argument("--train_batch", default=32, type=int)
    parser.add_argument("--valid_batch", default=32, type=int)
    parser.add_argument("--num_workers", default=10, type=int)
    parser.add_argument("--lr", default=1e-4, type=float)
    parser.add_argument("--weight_decay", default=1e-3, type=int)

    parser.add_argument('--optimizer',
                        choices=['SGD', 'Adam', 'AdaCubic'],
                        required=True)

    # model #
    parser.add_argument("--model", default="densenet", type=str,
                        choices=["DenseNet201", "ResNet50", "InceptionV3",
                                 "ResNet18", "MobileNetV3Small", "MobileNetV3Large", "SqueezeNet1_1"])

    parser.add_argument('--visual_content',
                        choices=['YT', 'WA', 'Native'], required=True)

    parser.add_argument("--n_fold", type=int, required=True)

    args = parser.parse_args()

    return args


def main():
    writer = SummaryWriter(comment=f"VISION-{args.visual_content}", log_dir=os.path.join(results_dir, 'logs'))

    print('Creating dataloader...')
    pkl_dir_tr = os.path.join(args.project_dir, 'preprocessed_images',
                              f"train_128images_{args.visual_content}_fold{args.n_fold}.pkl")

    train_set = ImageDataset(pkl_dir_tr, args.vision_frames_dir)
    print(f"Number of train samples {len(train_set)}")

    train_loader = DataLoader(train_set, shuffle=True,
                              batch_size=args.train_batch,
                              num_workers=args.num_workers,
                              pin_memory=True)

    pkl_dir_valid = os.path.join(args.project_dir,
                                 'preprocessed_images',
                                 f"valid_128images_{args.visual_content}_fold{args.n_fold}.pkl")

    valid_set = ImageDataset(pkl_dir_valid, args.vision_frames_dir)
    print(f"Number of Valid samples {len(valid_set)}")
    val_loader = DataLoader(valid_set, shuffle=True,
                            batch_size=args.valid_batch,
                            num_workers=args.num_workers,
                            pin_memory=True)

    print('Loading model...')
    if args.model == "DenseNet201":
        model = DenseNet201(weights=models.DenseNet201_Weights.DEFAULT, num_classes=train_set.n_classes).to(device)
    elif args.model == "ResNet50":
        model = ResNet50(weights=models.ResNet50_Weights.DEFAULT, num_classes=train_set.n_classes).to(device)
    elif args.model == "InceptionV3":
        model = InceptionV3(weights=models.Inception_V3_Weights.DEFAULT, num_classes=train_set.n_classes).to(device)
    elif args.model == "ResNet18":
        model = ResNet18(weights=models.ResNet18_Weights.DEFAULT, num_classes=train_set.n_classes).to(device)
    elif args.model == "MobileNetV3Small":
        model = MobileNetV3Small(weights=models.MobileNet_V3_Small_Weights.DEFAULT,
                                 num_classes=train_set.n_classes).to(device)
    elif args.model == "MobileNetV3Large":
        model = MobileNetV3Large(weights=models.MobileNet_V3_Large_Weights.DEFAULT,
                                 num_classes=train_set.n_classes).to(device)
    elif args.model == "SqueezeNet1_1":
        model = SqueezeNet1_1(weights=models.SqueezeNet1_1_Weights.DEFAULT,
                              num_classes=train_set.n_classes).to(device)

    print(model)

    loss_fn = nn.CrossEntropyLoss()

    # Optimizers
    if args.optimizer == 'SGD':
        optimizer = torch.optim.SGD(model.parameters(), lr=args.lr)
    elif args.optimizer == 'Adam':
        optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    elif args.optimizer == 'AdaCubic':
        raise ValueError('AdaCubic is published yet.')

        # eta1 = 0.05
        # eta2 = 0.75
        # alpha1 = 2.5  # very successful
        # alpha2 = 0.25  # unsuccessful

        # optimizer = AdaCubic(model.parameters(), eta1=eta1, eta2=eta2, alpha1=alpha1, alpha2=alpha2,
        #                      xi0=0.05, tol=1e-4, n_samples=1, average_conv_kernel=False, solver='exact',
        #                      kappa_easy=0.01, gamma1=0.25)

    best_acc = 0.0

    if not type(optimizer).__name__ == "AdaCubic":
        scheduler = MultiStepLR(optimizer, milestones=[30, 80], gamma=0.1)
    for epoch in range(args.epochs):
        train_loss, train_acc = training(model, device, train_loader, optimizer, loss_fn)
        valid_loss, valid_acc = validating(model, device, val_loader, loss_fn)
        if not type(optimizer).__name__ == "AdaCubic":
            scheduler.step()

        print(f"Epoch {epoch} Train Loss: {train_loss:.3f}"
              f" Train Acc: {100 * train_acc:.3f} "
              f"Valid Loss: {valid_loss:.3f}"
              f" Valid Acc: {100 * valid_acc:.3f}")

        is_best = (valid_acc > best_acc)
        if is_best:
            best_acc = valid_acc

        # save_checkpoint(state, is_best, split, checkpoint):
        save_checkpoint({"epoch": epoch + 1,
                         "state_dict": model.state_dict(),
                         'best_acc': best_acc,
                         "optimizer": optimizer.state_dict()},
                        is_best,
                        "{}".format(results_dir))
        writer.add_scalar("train loss", train_loss, epoch)
        writer.add_scalar("valid accuracy", valid_acc, epoch)

        with open(os.path.join(results_dir, 'tr_acc.log'), 'a') as outfile:
            outfile.write('{}\t{}\n'.format(epoch + 1, train_acc))

        with open(os.path.join(results_dir, 'val_acc.log'), 'a') as outfile:
            outfile.write('{}\t{}\n'.format(epoch + 1, valid_acc))

        with open(os.path.join(results_dir, 'tr_loss.log'), 'a') as outfile:
            outfile.write('{}\t{}\n'.format(epoch + 1, train_loss))
        with open(os.path.join(results_dir, 'val_loss.log'), 'a') as outfile:
            outfile.write('{}\t{}\n'.format(epoch + 1, valid_loss))

    writer.close()


if __name__ == '__main__':
    """
--visual_content
Native
--n_fold
0
--model
ResNet50
--project_dir
/media/blue/tsingalis/IARIADevIDFusion/image/
--epochs
100
--lr
1e-4
--vision_frames_dir
/media/red/sharedFolder/Datasets/VISION/keyframeExtraction/extractedFrames
--optimizer
Adam
--results_dir
/media/blue/tsingalis/IARIADevIDFusion/image/results/
    """
    args = get_args()

    results_dir = check_run_folder(os.path.join(args.results_dir, args.visual_content, f"fold{args.n_fold}"))

    with open(os.path.join(results_dir, 'args.json'), 'w') as fp:
        json.dump(vars(args), fp, indent=4)

    cuda_num = str(args.cuda)
    device = torch.device(f"cuda:{cuda_num}" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}")

    main()
