#%matplotlib inline
import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
from gammapy.image.utils import binary_dilation_circle
import gc

# Parameters
TOTAL_COUNTS = 1e6
SOURCE_FRACTION = 0.2

CORRELATION_RADIUS = 0.1 # deg
SIGNIFICANCE_THRESHOLD = 1.
MASK_DILATION_RADIUS = 5 # deg
NUMBER_OF_ITERATIONS = 3

# Derived parameters
DIFFUSE_FRACTION = 1. - SOURCE_FRACTION

# Load example model images
source_image_true = fits.getdata('sources.fits.gz')
diffuse_image_true = fits.getdata('diffuse.fits.gz')

# Generate example data
source_image_true *= SOURCE_FRACTION * TOTAL_COUNTS / source_image_true.sum()
diffuse_image_true *= DIFFUSE_FRACTION * TOTAL_COUNTS / diffuse_image_true.sum()
total_image_true = source_image_true + diffuse_image_true

counts = np.random.poisson(total_image_true)

print('source counts: {0}'.format(source_image_true.sum()))
print('diffuse counts: {0}'.format(diffuse_image_true.sum()))

# If you want to check the input images plot them here:
#plt.figure(figsize=(0,10))
#plt.imshow(source_image_true)
#plt.imshow(np.log(counts))

import logging
logging.basicConfig(level=logging.INFO)
from scipy.ndimage import convolve
from gammapy.stats import significance

class GammaImages(object):
    """Container for a set of related images.
    
    Meaning of mask:
    * 1 = background region
    * 0 = source region
    (such that multiplying with the mask zeros out the source regions)

    TODO: document
    """
    def __init__(self, counts, background=None, mask=None):
        self.counts = np.asarray(counts, dtype=float)

        if background == None:
            # Start with a flat background estimate
            self.background = np.ones_like(background, dtype=float)
        else:
            self.background = np.asarray(background, dtype=float)

        if mask == None:
            self.mask = np.ones_like(counts, dtype=bool)
        else:
            self.mask = np.asarray(mask, dtype=bool)
    
    def compute_correlated_maps(self, kernel):
        """Compute significance image for a given kernel.
        """
        self.counts_corr = convolve(self.mask * self.counts, kernel)
        self.background_corr = convolve(self.mask * self.background, kernel)#/convolve(self.background, self.mask)
        self.significance = significance(self.counts_corr, self.background_corr)#kernal? sk?

        return self

    def print_info(self):
        logging.info('Counts sum: {0}'.format(self.counts.sum()))
        logging.info('Background sum: {0}'.format(self.background.sum()))
        background_fraction = 100. * self.background.sum() / self.background.sum()
        logging.info('Background fraction: {0}'.format(background_fraction))
        excluded_fraction = 100. * np.mean(self.mask)
        logging.info('Mask fraction: {0}%'.format(excluded_fraction))
    
    def save(self, filename):
        logging.info('Writing {0}'.format(filename))
        
class IterativeBackgroundEstimator(object):
    """Iteratively estimate a background model.

    TODO: document

    Parameters
    ----------
    image : `GammaImages`
        Gamma images

    See also
    --------
    `gammapy.detect.CWT`
    """
    def __init__(self, images, source_kernel, background_kernel,
                 significance_threshold, mask_dilation_radius,
                 delete_intermediate_results=True):
        
        # self._data[i] is a GammaImages object representing iteration number `i`.
        self._data = list()
        self._data.append(images)
        
        self.source_kernel = source_kernel
        self.background_kernel = background_kernel

        self.significance_threshold = significance_threshold
        self.mask_dilation_radius = mask_dilation_radius
        
        self.delete_intermediate_results = delete_intermediate_results
        
        gc.collect()
    
    def run(self, n_iterations, filebase):
        """Run N iterations."""
        reference_hdu = fits.open('sources.fits.gz')[1]
        logging.info('Writing {0}'.format(filebase))
        for ii in range(n_iterations):
            logging.info('Running iteration #{0}'.format(ii))
            self.run_iteration()
            filename = filebase + '{0:02d}counts'.format(ii) + '.fits'
            reference_hdu.data = images.counts
            reference_hdu.writeto(filename, clobber=True)
            filename = filebase + '{0:02d}background'.format(ii) + '.fits'
            reference_hdu.data = images.background
            reference_hdu.writeto(filename, clobber=True)
            filename = filebase + '{0:02d}mask'.format(ii) + '.fits'
            reference_hdu.data = images.mask.astype(int)
            reference_hdu.writeto(filename, clobber=True)
            if self.delete_intermediate_results:
                # Remove results from previous iteration
                del self._data[0]
                gc.collect()

    def run_iteration(self):
        """Run one iteration."""
        # Start with images from the last iteration
        images = self._data[-1]
        
        logging.info('*** INPUT IMAGES ***')
        images.print_info()

        # Compute new exclusion mask:
        # Threshold and dilate old significance image
        logging.info('Computing source kernel correlated images.')
        images = images.compute_correlated_maps(self.source_kernel)

        logging.info('Computing new exclusion mask')
        mask = np.where(images.significance > self.significance_threshold, 0, 1)#.astype(int)
        mask = binary_dilation_circle(mask, radius=self.mask_dilation_radius)
        
        # Compute new background estimate:
        # Convolve old background estimate with background kernel,
        # excluding sources via the old mask.
        background_corr = convolve(images.mask * images.counts, self.background_kernel)
        denom = convolve(images.mask, self.background_kernel)
        #denom = background.mean()/background.size
        background = background_corr / denom.astype(int).mean()
        #import IPython; IPython.embed()
        
        # Store new images
        images = GammaImages(counts, background, mask)
        logging.info('*** OUTPUT IMAGES ***')
        images.print_info()
        self._data.append(images)
    
    #def save(self, filebase):
        
        #for ii, images in enumerate(self._data):
            

if __name__ == '__main__':
    # Start with flat background estimate
    background=np.ones_like(counts, dtype=float)
    images = GammaImages(counts=counts, background=background)

    # CORRELATION_RADIUS
    source_kernel = (np.ones((5, 5)))/(np.ones((5, 5)).sum())

    background_kernel = np.ones((100, 10))

    ibe = IterativeBackgroundEstimator(
                                       images=images,
                                       source_kernel=source_kernel,
                                       background_kernel=background_kernel,
                                       significance_threshold=SIGNIFICANCE_THRESHOLD,
                                       mask_dilation_radius=MASK_DILATION_RADIUS
                                       )

    ibe.run(n_iterations=4, filebase='test')

    ibe.run_iteration()
    #import IPython; IPython.embed()
    #ibe.save('test')
    
    #counts_hdu = background_hdu = mask_hdu = fits.open('sources.fits.gz')[1]
    #counts_hdu.data = images.counts
    #counts_hdu.writeto('testcounts.fits', clobber=True)
    #background_hdu.data = images.counts
    #background_hdu.writeto('testbackground.fits', clobber=True)
    #mask_hdu.data = images.mask.astype(int)
    #mask_hdu.writeto('testmask.fits', clobber=True)
