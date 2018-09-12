import os
import numpy as np
from tqdm import tqdm
import ersa_utils
import processBlock


def make_grid(tile_size, patch_size, overlap):
    """
    Extract patches at fixed locations. Output coordinates for Y,X as a list (not two lists)
    :param tile_size: size of the tile (input image)
    :param patch_size: size of the output patch
    :param overlap: #overlapping pixels
    :return:
    """
    max_h = tile_size[0] - patch_size[0]
    max_w = tile_size[1] - patch_size[1]
    if max_h > 0 and max_w > 0:
        h_step = np.ceil(tile_size[0] / (patch_size[0] - overlap))
        w_step = np.ceil(tile_size[1] / (patch_size[1] - overlap))
    else:
        h_step = 1
        w_step = 1
    patch_grid_h = np.floor(np.linspace(0, max_h, h_step)).astype(np.int32)
    patch_grid_w = np.floor(np.linspace(0, max_w, w_step)).astype(np.int32)

    y, x = np.meshgrid(patch_grid_h, patch_grid_w)
    return list(zip(y.flatten(), x.flatten()))


def patch_block(block, pad, grid_list, patch_size, return_coord=False):
    """
    make a data block into patches
    :param block: data block to be patched, shold be h*w*c
    :param pad: #pixels to pad around
    :param grid_list: list of grids
    :param patch_size: size of the patch
    :param return_coord: if True, coordinates of x and y will be returned
    :return: yields patches or as well as x and y coordinates
    """
    # pad image first if it is necessary
    if pad > 0:
        block = ersa_utils.pad_image(block, pad)
    # extract images
    for y, x in grid_list:
        patch = ersa_utils.crop_image(block, y, x, patch_size[0], patch_size[1])
        if return_coord:
            yield patch, y, x
        else:
            yield patch


def unpatch_block(blocks, tile_dim, patch_size, tile_dim_output=None, patch_size_output=None, overlap=0):
    """
    Unpatch a block, set tile_dim_output and patch_size_output to a proper number if padding exits
    :param blocks: data blocks, should be n*h*w*c
    :param tile_dim: input tile dimension, if padding exits should be h+2*pad, w+2*pad
    :param patch_size: input patch size
    :param tile_dim_output: output tile dimension
    :param patch_size_output: output patch dimension, if shrinking exits, should be h-2*pd, w-2*pad
    :param overlap: overlap of adjacent patches
    :return:
    """
    if tile_dim_output is None:
        tile_dim_output = tile_dim
    if patch_size_output is None:
        patch_size_output = patch_size
    _, _, _, c = blocks.shape
    image = np.zeros((tile_dim_output[0], tile_dim_output[1], c))
    for cnt, (corner_h, corner_w) in enumerate(make_grid(tile_dim, patch_size, overlap)):
        image[corner_h:corner_h + patch_size_output[0], corner_w:corner_w + patch_size_output[1], :] \
            += blocks[cnt, :, :, :]
    return image


class PatchExtractor(processBlock.BasicProcess):
    """
    Extract patches from images in a densely sliding window
    """
    def __init__(self, patch_size, tile_size, ds_name, overlap=0, pad=0, name='patch_extractor'):
        """
        :param patch_size: patch size to be extracted
        :param tile_size: tile size (image size)
        :param ds_name: name of the dataset, it will be used to name the folder
        :param overlap: #overlapping pixels
        :param pad: #pxiels to pad around the iamge
        :param name: name of the process
        """
        self.patch_size = np.array(patch_size, dtype=np.int32)
        self.tile_size = np.array(tile_size, dtype=np.int32)
        self.overlap = overlap
        self.pad = pad
        pe_name = '{}_h{}w{}_overlap{}_pad{}'.format(name, self.patch_size[0], self.patch_size[1], self.overlap, self.pad)
        path = ersa_utils.get_block_dir('data', [name, ds_name, pe_name])
        super().__init__(pe_name, path, func=self.process)

    def process(self, **kwargs):
        """
        Extract the patches
        :param kwargs:
            file_list: list of lists of the files, can be generated by using collectionMaker.load_files()
            file_exts: extensions of the new files
        :return:
        """
        assert len(kwargs['file_exts']) == len(kwargs['file_list'][0])
        grid_list = make_grid(self.tile_size + 2*self.pad, self.patch_size, self.overlap)
        pbar = tqdm(kwargs['file_list'])
        record_file = open(os.path.join(self.path, 'file_list.txt'), 'w')
        for files in pbar:
            pbar.set_description('Extracting {}'.format(os.path.basename(files[0])))
            patch_list = []
            for f, ext in zip(files, kwargs['file_exts']):
                patch_list_ext = []
                img = ersa_utils.load_file(f)
                # extract images
                for patch, y, x in patch_block(img, self.pad, grid_list, self.patch_size, return_coord=True):
                    patch_name = '{}_y{}x{}.{}'.format(os.path.basename(f).split('.')[0], int(y), int(x), ext)
                    patch_name = os.path.join(self.path, patch_name)
                    ersa_utils.save_file(patch_name, patch.astype(np.uint8))
                    patch_list_ext.append(patch_name)
                patch_list.append(patch_list_ext)
            patch_list = ersa_utils.rotate_list(patch_list)
            for items in patch_list:
                record_file.write('{}\n'.format(' '.join(items)))
        record_file.close()

    def get_filelist(self):
        """
        Get the list of lists of patches extracted
        An assertion error will raise if process finish check failed
        :return:list of lists
        """
        if self.check_finish():
            with open(os.path.join(self.path, 'file_list.txt'), 'r') as record_file:
                f_list = record_file.readlines()
            f_list = [l.strip().split(' ') for l in f_list]
            return f_list
        else:
            raise AssertionError('Need to run patch extractor first')
