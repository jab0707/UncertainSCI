import numpy as np

from opoly1d import OrthogonalPolynomialBasis1D

from utils.linalg import greedy_d_optimal

def opolynd_eval(x, lambdas, ab):
    # Evaluates tensorial orthonormal polynomials associated with the
    # univariate recurrence coefficients ab.

    try:
        M, d = x.shape
    except Exception:
        d = x.size
        M = 1
        x = np.reshape(x, (M, d))

    N, d2 = lambdas.shape

    assert d==d2, "Dimension 1 of x and lambdas must be equal"

    p = np.ones([M, N])

    for qd in range(d):
        p = p * opoly1d.opoly1d_eval(x[:,qd], lambdas[:,qd], ab)

    return p

class TensorialPolynomials:
    def __init__(self, polys1d = None, dim = None):

        if polys1d is None:
            raise TypeError('A one-dimemsional polynomial family is required.')

        # Isotropic tensorization of 1D family
        elif isinstance(polys1d, OrthogonalPolynomialBasis1D):
            self.polys1d = polys1d
            self.isotropic = True
            if dim is None:
                self.dim = 1
            else:
                self.dim = dim

        # Anistropic tensorization of 1D family
        elif isinstance(polys1d, list) or isinstance(polys1d, tuple):
            if dim is not None:
                raise ValueError('If polys1d is a list/tuple, the scalar dim cannot be set.')
            for item in polys1d:
                if not isinstance(item, OrthogonalPolynomialBasis1D):
                    raise ValueError('Elements of polys1d must be OrthogonalPolynomialBasis1D objects')
            self.polys1d = list(polys1d)
            self.isotropic = False
            self.dim = len(self.polys1d)

        else: 
            raise TypeError('Unrecognized type for input polys1d')

    def eval(self, x, lambdas):
        """
        Evaluates tensorial orthonormal polynomials.
        """
        
        try:
            M, d = x.shape
        except Exception:
            d = x.size
            M = 1
            x = np.reshape(x, (M, d))
    
        N, d2 = lambdas.shape
    
        assert d==d2==self.dim, "Dimension 0 of both x and lambdas must equal self.dim"
    
        p = np.ones([M, N])
    
        if self.isotropic:
            for qd in range(self.dim):
                p = p * self.polys1d.eval(x[:,qd], lambdas[:,qd])
        else:
            for qd in range(self.dim):
                p = p * self.polys1d[qd].eval(x[:,qd], lambdas[:,qd])
    
        return p

    def idist_mixture_sampling(self, M, Lambdas, fast_sampler=True):
        """
        Performs tensorial inverse transform sampling from an additive mixture of
        tensorial induced distributions, generating M samples
        
        The measure this samples from is the order-Lambdas induced measure, which
        is an additive mixture of tensorial measures
        
        Each tensorial measure is defined a row of Lambdas
        
        Parameters
        ------
        param1: M
        Number of samples to generate
        param2: Lambdas
        Sample from the order-Lambdas induced measure
        
        Returns
        ------
        """

        K, d = Lambdas.shape

        assert M>0 and d==self.dim

        # Randomly select M indices from Lambdas
        ks = np.ceil(K * np.random.random(M)).astype(int)
        ks[np.where(ks > K)] = K
        Lambdas = Lambdas[ks-1, :]



        if self.isotropic:
            if fast_sampler:
                idistinv = self.polys1d.fidistinv
            else:
                idistinv = self.polys1d.idistinv

            univ_inv = lambda uu,nn: idistinv(uu, nn)
            return univ_inv(np.random.random([M,d]), Lambdas)

        else:
            x = np.zeros([M, d])
            for qd in range(self.dim):
                if fast_sampler:
                    idistinv = self.polys1d[qd].fidistinv
                else:
                    idistinv = self.polys1d[qd].idistinv

                univ_inv = lambda uu,nn: idistinv(uu, nn)
                x[:,qd] = univ_inv(np.random.random(M), Lambdas[:,qd])
            return x

    def wafp_sampling(self, indices, oversampling=10, sampler='idist', K=None, fast_sampler=True):
        """
        Computes (indices.shape[0] + oversampling) points using the WAFP
        strategy. This requires forming K random samples; the input sampler
        determines which measure to take these random samples from.
        """

        M = indices.shape[0] + oversampling

        if K is None:
            K = M + 40
        else:
            K = max(K, M)

        if sampler == 'idist':
            x = self.idist_mixture_sampling(K, indices, fast_sampler=fast_sampler)
        else:
            raise ValueError('Unrecognized string "{0:s}" for input "sampler"'.format(sampler))

        V = self.eval(x, indices)

        # Precondition rows to have unit norm
        V = np.multiply(V.T, 1/np.sqrt(np.sum(V**2, axis=1))).T

        P = greedy_d_optimal(V, M)

        return x[P,:]

if __name__ == "__main__":

    import matplotlib.pyplot as plt
    from matplotlib import cm
    from mpl_toolkits.mplot3d import Axes3D
    from families import JacobiPolynomials
    import opoly1d, indexing

    import pdb

    d = 4
    k = 3

    J = JacobiPolynomials()
    P = TensorialPolynomials(J, d)
    #ab = opoly1d.jacobi_recurrence(k+1, alpha=0, beta=0)

    lambdas = indexing.total_degree_indices(d, k)

    if d == 2:
        N = 50
        x = np.linspace(-1, 1, N)
        X,Y = np.meshgrid(x,x)

        XX = np.concatenate((X.reshape(X.size,1), Y.reshape(Y.size,1)), axis=1)


        p = P.eval(XX, lambdas)

        fig = plt.figure()
        ax = fig.gca(projection='3d')
        ax.plot_surface(X, Y, p[:,j].reshape(N,N), cmap=cm.coolwarm, linewidth=0,antialiased=True)
        plt.show()

    x2 = P.idist_mixture_sampling(10, lambdas)

    x3 = P.wafp_sampling(lambdas)
