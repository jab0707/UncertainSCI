from packaging import version 
from math import floor

import numpy as np

from indexing import MultiIndexSet
from distributions import ProbabilityDistribution

class PolynomialChaosExpansion():
    def __init__(self, indices=None, distribution=None):

        self.coefficients = None
        self.indices, self.distribution = indices, distribution

    def set_indices(self, indices):

        if isinstance(indices, MultiIndexSet):
            self.indices = indices
        else:
            raise ValueError('Indices must be a MultiIndexSet object')

    def set_distribution(self, distribution):

        if isinstance(distribution, ProbabilityDistribution):
            self.distribution = distribution
        else:
            raise ValueError('Distribution must be a ProbabilityDistribution object')

    def build_pce_wafp(self, model, samples=None, **sampler_options):
        """
        Computes PCE coefficients. Uses a WAFP grid to compute a least-squares
        collocation solution.

        model should have the syntax:

        output = model(input_parmaeter_value),

        where input_parameter_value is a vector of size self.dim containing a
        parametric sample, and output is a 1D numpy array.
        """

        if self.indices is None:
            raise ValueError('First set indices with set_indices')
        if self.distribution is None:
            raise ValueError('First set distribution with set_distribution')

        # Samples on standard domain
        if samples is None:
            p_standard = self.distribution.polys.wafp_sampling(self.indices.indices(), **sampler_options)

            # Maps to domain
            p = self.distribution.transform_to_standard.mapinv( \
                    self.distribution.transform_standard_dist_to_poly.mapinv(p_standard) )
        else:
            p = samples
            if p.shape[1] != self.indices.indices().shape[1]:
                raise ValueError('Input parameter samples p have wrong dimension')
            p_standard = self.distribution.transform_standard_dist_to_poly.map( \
                    self.distribution.transform_to_standard.map( p ) )

        output = None

        for ind in range(p.shape[0]):
            if output is None:
                output = model(p[ind,:])
                M = output.size
                output = np.concatenate( [ output.reshape([1, M]), np.zeros([p.shape[0]-1, M]) ], axis=0 )
            else:
                output[ind,:] = model(p[ind,:])

        V = self.distribution.polys.eval(p_standard, self.indices.indices())

        # Precondition for stability
        norms = 1/np.sqrt(np.sum(V**2, axis=1))
        V = np.multiply(V.T, norms).T
        output = np.multiply(output.T, norms).T

        if version.parse(np.__version__) < version.parse('1.14.0'):
            coeffs,residuals = np.linalg.lstsq(V, output, rcond=-1)[:2]
        else:
            coeffs,residuals = np.linalg.lstsq(V, output, rcond=None)[:2]

        self.coefficients = coeffs
        self.p = p
        self.output = np.multiply(output.T, 1/norms).T

        return residuals

    def build(self, model, **options):
        """
        Builds PCE from sampling and approximation settings.
        """

        # For now, we only have 1 method:
        return self.build_pce_wafp(model, **options)

    def assert_pce_built(self):
        if self.coefficients is None:
            raise ValueError('First build the PCE with pce.build()')

    def mean(self):
        """
        Returns PCE mean.
        """

        self.assert_pce_built()
        return self.coefficients[0,:]

    def stdev(self):
        """
        Returns PCE standard deviation
        """

        self.assert_pce_built()
        return np.sqrt(np.sum(self.coefficients[1:,:]**2, axis=0))

    def pce_eval(self, p, components=None):
        """
        Evaluations the PCE at the parameter locations p.
        """

        self.assert_pce_built()
        p_std = self.distribution.transform_to_standard.map( \
                    self.distribution.transform_standard_dist_to_poly.map(p) )

        if components is None:
            return np.dot( self.distribution.polys.eval( p_std, self.indices.indices() ), self.coefficients)
        else:
            return np.dot( self.distribution.polys.eval( p_std, self.indices.indices() ), self.coefficients[:,components])

    def quantile(self, q, M=100):
        """
        Computes q-quantiles using M-point Monte Carlo sampling.
        """

        self.assert_pce_built()

        # Maximum number of floats generated at any given time
        MF = max([int(1e6), M, self.distribution.dim])

        # How many model degrees of freedom we can consider at any time
        pce_batch_size = floor(MF/M)

        quantiles = np.zeros([len(q), self.coefficients.shape[1]])

        pce_counter = 0
        p = self.distribution.MC_samples(M)

        while pce_counter < self.coefficients.shape[1]:
            end_ind = min([self.coefficients.shape[1], pce_counter + pce_batch_size])
            inds = range(pce_counter, end_ind)
            ensemble = self.pce_eval(p, components=inds)

            quantiles[:, inds] = np.quantile(ensemble, q, axis=0)

            pce_counter = end_ind

        return quantiles

    def total_sensitivity(self, dim_indices = None):
        """
        Computes total sensitivity associated to dimensions dim_indices from
        PCE coefficients. dim_indices should be a list-type containing
        dimension indices.

        The output is len(js) x self.coefficients.shape[1]
        """

        self.assert_pce_built()

        if dim_indices is None:
            dim_indices = range(self.distribution.dim)

        dim_indices = np.asarray(dim_indices,dtype=int)

        indices = self.indices.indices()
        variance_rows = np.linalg.norm(indices, axis=1) > 0.

        #variances = np.sum(self.coefficients[variance_rows,:]**2, axis=0)
        variance = self.stdev()**2
        total_sensitivities = np.zeros([dim_indices.size, self.coefficients.shape[1]])

        for (qj,j) in enumerate(dim_indices):
            total_sensitivities[qj,:] = np.sum(self.coefficients[indices[:,j]>0,:]**2, axis=0)/variance

        return total_sensitivities

    def global_sensitivity(self, dim_lists=None):
        """
        Computes global sensitivity associated to dimensional indices dim_lists
        from PCE coefficients. 

        dim_lists should be a list of index lists. The global sensitivity for each
        index list is returned.
        The output is len(dim_lists) x self.coefficients.shape[1]
        """

        #unique_rows = np.vstack({tuple(row) for row in lambdas})
        ## Just making sure
        #assert unique_rows.shape[0] == lambdas.shape[0]

        indices = self.indices.indices()
        variance_rows = np.linalg.norm(indices, axis=1) > 0.
        #assert np.sum(np.invert(variance_rows)) == 1

        variance = self.stdev()**2
        global_sensitivities = np.zeros([len(dim_lists), self.coefficients.shape[1]])
        dim = self.distribution.dim
        for (qj,j) in enumerate(dim_lists):
            jc = np.setdiff1d(range(dim), j)
            inds = np.logical_and( np.all(indices[:,j] > 0, axis=1), \
                                   np.all(indices[:,jc]==0, axis=1) )
            global_sensitivities[qj,:] = np.sum(self.coefficients[inds,:]**2, axis=0)/variance

        return global_sensitivities
