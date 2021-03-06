from CSDGAN.classes.image.ImageDataset import ImageFolderWithPaths, ImageFolder
import utils.image_utils as iu
import utils.utils as uu
import CSDGAN.utils.constants as cs

from torch.utils import data
import torchvision
from sklearn.model_selection import train_test_split
import shutil
import torchvision.transforms as t
import pandas as pd
import os


def import_dataset(path, bs, shuffle, incl_paths):
    """
    Image generator for a directory containing folders as label names (and images of that label within each of these label-named folders)
    :param path: Path to parent directory
    :param bs: Batch size
    :param shuffle: Whether to shuffle the data order
    :param incl_paths: Whether to use ImageFolderWithPaths or simply ImageFolder (the former returns the path to each image as a third item in the iterator).
    :return: PyTorch DataLoader
    """
    if incl_paths:
        dataset = ImageFolderWithPaths(
            root=path,
            transform=torchvision.transforms.ToTensor()
        )
    else:
        dataset = ImageFolder(
            root=path,
            transform=torchvision.transforms.ToTensor()
        )
    loader = data.DataLoader(
        dataset,
        batch_size=bs,
        num_workers=0,
        shuffle=shuffle
    )
    return loader


def preprocess_imported_dataset(path, import_gen, splits=None, x_dim=None):
    """
    Preprocesses entire image data set, cropping images and splitting them into train and validation folders.
    Returns import information for future steps
    1. Scan data set and map it by label
    2. Split into train/val/test
    3. Encodes labels for one hot encoding
    4. Initializes directories
    5. Preprocesses images and save to directory
    6. Delete original images

    :param path: Path where unprocessed images are located and where processed images will be saved
    :param import_gen: PyTorch DataLoader with raw images
    :param splits: Train/Validation/Test Splits
    :param x_dim: Desired dimensions of image. If None, dimensions of first image are used.
    :return: Tuple of label encoder, one hot encoder, and image dimensions
    """
    if splits is None:
        splits = cs.IMAGE_DEFAULT_TRAIN_VAL_TEST_SPLITS  # Default

    assert round(sum(splits), 5) == 1.0
    assert len(splits) == 3

    # Scan data set, create table mapping it out by label
    dataset_map, labels = scan_image_dataset(path)
    train_val_map, test_map = train_test_split(dataset_map, test_size=splits[2], shuffle=True, stratify=dataset_map['label'])
    train_map, val_map = train_test_split(train_val_map, test_size=splits[1] / (splits[0]+splits[1]), stratify=train_val_map['label'])
    train_map['split'], val_map['split'], test_map['split'] = 'train', 'val', 'test'
    dataset_map = pd.concat((train_map, val_map, test_map), axis=0)
    dataset_map.sort_index(inplace=True)
    dataset_map.set_index(keys=['id', 'label'], inplace=True)

    # Set up paths for image folder
    os.makedirs(os.path.join(path, "train"), exist_ok=True)
    os.makedirs(os.path.join(path, "val"), exist_ok=True)
    os.makedirs(os.path.join(path, "test"), exist_ok=True)

    for label in labels:
        os.makedirs(os.path.join(path, "train", label), exist_ok=True)
        os.makedirs(os.path.join(path, "val", label), exist_ok=True)
        os.makedirs(os.path.join(path, "test", label), exist_ok=True)

    _, le, ohe = uu.encode_y(labels)

    # Determine crop size if not given
    if x_dim is None:
        x_dim = find_first_img_dim(import_gen=import_gen)

    # Determine ideal crop size based on architecture
    h_best_crop, _, _ = iu.find_pow_2_arch(x_dim[0])
    w_best_crop, _, _ = iu.find_pow_2_arch(x_dim[1])

    # Initialize transformer
    transformer = t.Compose([
        t.ToPILImage(),
        t.CenterCrop((x_dim[0] - h_best_crop, x_dim[1] - w_best_crop))
    ])

    # Preprocess images and save into train/val folders
    for x, y, img_ids in import_gen:
        for i in range(len(x)):
            img = transformer(x[i])
            label = le.inverse_transform(y[i].view(-1)).take(0)
            split = dataset_map.loc[img_ids[i], label].values.take(0)
            img.save(os.path.join(path, split, label, img_ids[i]))

    # Delete original images to save space
    for label in labels:
        shutil.rmtree(os.path.join(path, label))

    return le, ohe, (x_dim[0] - h_best_crop, x_dim[1] - w_best_crop)


def scan_image_dataset(path):
    """
    Loops through image data set and produces a table with info about the data set
    Assumes all extensions are the same
    :param path: Path to image data set
    :return: Tuple of table with one row per image, with file name and label as features, and a vector of labels
    """
    labels = sorted(os.listdir(path))

    dict = {'id': [], 'label': []}
    for label in labels:
        tmp_ids = os.listdir(os.path.join(path, label))
        tmp_labels = [label for id in tmp_ids]
        dict['id'] += tmp_ids
        dict['label'] += tmp_labels

    df = pd.DataFrame(data=dict)

    return df, labels


def find_img_folder_name(data_dir):
    """Loops through contents of unzipped data folder and returns the first folder it finds"""
    return [name for name in os.listdir(data_dir) if os.path.isdir(os.path.join(data_dir, name))][0]


def find_first_img_dim(import_gen):
    """
    Loads in the first image in a provided data set and returns its dimensions
    Intentionally returns on first iteration of the loop
    :param import_gen: PyTorch DataLoader utilizing ImageFolderWithPaths for its dataset
    :return: dimensions of image
    """
    for x, _, _ in import_gen:
        return x[0].shape[-2], x[0].shape[-1]


def find_first_img_num_channels(import_gen):
    """
    Loads in the first image in a provided data set and returns its number of channels
    Intentionally returns on first iteration of the loop
    :param import_gen: PyTorch DataLoader utilizing ImageFolderWithPaths for its dataset
    :return: dimensions of image
    """
    for x, _, _ in import_gen:
        return x[0].shape[0]
