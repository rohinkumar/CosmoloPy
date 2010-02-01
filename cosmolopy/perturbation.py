"""Routines related to perturbation theory and the power spectrum.

This module relies largely on code from:

Eisenstein & Hu (1999 ApJ 511 5)

http://background.uchicago.edu/~whu/transfer/transferpage.html

You need to download this code for many functions to work. See
EH/installation.txt for installation instructions.

"""

import math
import warnings

import numpy
import scipy
import scipy.special
import scipy.integrate as si

import constants as cc
import density as cden

try:
    import EH.power as power
except ImportError:
    print "Error importing EH.power. See EH/installation.txt."
    print "Some functions will not work." 

# Turn on printing of special function error messages.
scipy.special.errprint(1)

def transfer_function_EH(k, **cosmology):
    """
    Calculate the transfer function as a function of wavenumber k.

    Parameters:
    ----------

    cosmology : dict 
       Specify the cosmological parameters with the keys 'omega_M_0',
       'omega_b_0', 'omega_n_0', 'N_nu', 'omega_lambda_0', and 'h'.
    
    k : array
       Wavenumber in Mpc^-1.

    Returns:
    -------

    A tupple of arrays matching the shape of k, the first is the
    transfer function for CDM + Baryons, the second is for CDM +
    Baryons + Neutrinos.

    Notes:
    -----

    Uses transfer function code from Eisenstein & Hu (1999 ApJ 511 5)

    See power.c from

    http://background.uchicago.edu/~whu/transfer/transferpage.html

    and perturbation_installation.txt in this directory.

    """
    k = numpy.atleast_1d(k)
    
    z_val=0

    # /* TFmdm_set_cosm() -- User passes all the cosmological parameters as
    # 	arguments; the routine sets up all of the scalar quantites needed 
    # 	computation of the fitting formula.  The input parameters are: 
    # 	1) omega_matter -- Density of CDM, baryons, and massive neutrinos,
    # 				in units of the critical density. 
    # 	2) omega_baryon -- Density of baryons, in units of critical. 
    # 	3) omega_hdm    -- Density of massive neutrinos, in units of critical 
    # 	4) degen_hdm    -- (Int) Number of degenerate massive neutrino species 
    # 	5) omega_lambda -- Cosmological constant 
    # 	6) hubble       -- Hubble constant, in units of 100 km/s/Mpc 
    # 	7) redshift     -- The redshift at which to evaluate */
    if int(cosmology['N_nu']) != cosmology['N_nu']:
        raise TypeError('N_nu must be an integer.')
    power.TFmdm_set_cosm(cosmology['omega_M_0'], cosmology['omega_b_0'], 
                         cosmology['omega_n_0'],  int(cosmology['N_nu']), 
                         cosmology['omega_lambda_0'], cosmology['h'], 
                         z_val)
    
    # Given a wavenumber in Mpc^-1, return the transfer function for
    # the cosmology held in the global variables.
    pfunc = numpy.vectorize(lambda k: (power.TFmdm_onek_mpc(k), 
                                       power.cvar.tf_cbnu))
    transFunc = pfunc(k)
    return transFunc

def fgrowth(z, omega_M_0, unnormed=False):
    r"""Cosmological perturbation growth factor, normalized to 1 at z = 0.
    
    Approximate forumla from Carol, Press, & Turner (1992, ARA&A, 30,
    499), "good to a few percent in regions of plausible Omega_M,
    Omega_Lambda".

    This is proportional to D_1(z) from Eisenstein & Hu (1999 ApJ 511
    5) equation 10, but the normalization is different: fgrowth = 1 at
    z = 0 and :math:`D_1(z) = \frac{1+z_\mathrm{eq}}{1+z}` as z goes
    to infinity.
    
    To get D_1 one would just use 
    
    .. math:
    
        D_1(z) = (1+z_\mathrm{eq}) \mathtt{fgrowth}(z,\Omega_{M0}, 1)

    (see \EH\ equation 1 for z_eq).

    .. math:
    
        \mathtt{fgrowth} = \frac{D_1(z)}{D_1(0)}

    Setting unnormed to true turns off normalization.

    Note: assumes Omega_lambda_0 = 1 - Omega_M_0!
    
    """
    #if cden.get_omega_k_0(**) != 0:
    #    raise ValueError, "Not valid for non-flat (omega_k_0 !=0) cosmology."

    omega = cden.omega_M_z(z, omega_M_0=omega_M_0, omega_lambda_0=1.-omega_M_0)
    lamb = 1 - omega
    a = 1/(1 + z)

    if unnormed:
        norm = 1.0
    else:
        norm = 1.0 / fgrowth(0.0, omega_M_0, unnormed=True) 
    return (norm * (5./2.) * a * omega / 
            (omega**(4./7.) - lamb + (1. + omega/2.) * (1. + lamb/70.))
            )

def w_tophat(k, r):
    r"""Calculate the k-space Fourier transform of a spherical tophat.

    Parameters:
    ----------
    
    k: array
      wavenumber

    r: array
       radius of the 3-D spherical tophat

    Note: k and r need to be in the same units.

    Returns:
    -------
    
    :math:`\tilde{w}`: array
       the value of the transformed function at wavenumber k.
    
    """
    return (3. * ( numpy.sin(k * r) - k * r * numpy.cos(k * r) ) / 
            ((k * r)**3.))


def _sigmasq_integrand_log(logk, r, cosmology):
    """Integrand used internally by the sigma_r function.
    """
    k = numpy.exp(logk)
    # The 1e-10 factor in the integrand is added to avoid roundoff
    # error warnings. It is divided out later.
    return (k *
            (1.e-10 / (2. * math.pi**2.)) * k**2. * 
            w_tophat(k, r)**2. * 
            power_spectrum(k, 0.0, **cosmology))

def _klims(r, cosmology):
    """Integration limits used internally by the sigma_r function."""
    logk = numpy.arange(-20., 20., 0.1)
    integrand = _sigmasq_integrand_log(logk, r, cosmology)

    maxintegrand = numpy.max(integrand)
    factor = 1.e-4
    highmask = integrand > maxintegrand * factor
    while highmask.ndim > logk.ndim:
        highmask = numpy.logical_or.reduce(highmask)

    mink = numpy.min(logk[highmask])
    maxk = numpy.max(logk[highmask])

    return mink, maxk
 
def _sigmasq_r_scalar(r, 
                      n, deltaSqr, omega_M_0, omega_b_0, omega_n_0, N_nu, 
                      omega_lambda_0, h):
    """Calculate sigma_r^2 at z=0. Works only for scalar r. 

    Used internally by the sigma_r function.

    Parameters:
    ----------
    
    r : array
       radius in Mpc.

    n, omega_M_0, omega_b_0, omega_n_0, N_nu, omega_lambda_0, h:
       cosmological parameters, specified like this to allow this
       function to be vectorized (see source code of sigma_r).

    Returns:
    -------

    sigma^2, error(sigma^2)

    """
    # r is in Mpc, so k will also by in Mpc for the integration.

    cosmology = {'n':n, 
                 'deltaSqr':deltaSqr,
                 'omega_M_0':omega_M_0, 
                 'omega_b_0':omega_b_0, 
                 'omega_n_0':omega_n_0, 
                 'N_nu':N_nu, 
                 'omega_lambda_0':omega_lambda_0, 
                 'h':h,}
    logk_lim = _klims(r, cosmology)
    #print "Integrating from logk = %.1f to %.1f." % logk_lim
    
    # Integrate over logk from -infinity to infinity.
    integral, error = si.quad(_sigmasq_integrand_log, 
                              logk_lim[0], 
                              logk_lim[1], 
                              args=(r, cosmology),
                              limit=10000)#, epsabs=1e-9, epsrel=1e-9)
    return 1.e10 * integral, 1.e10 * error

def sigma_r(r, z, **cosmology):
    r"""RMS mass fluctuations of a sphere of radius r at redshift z.

    Returns sigma and the error on sigma.
    
    Parameters:
    ----------
    
    r : array
       radius of sphere in Mpc

    z : array
       redshift

    Returns:
    -------

    sigma:
       RMS mass fluctuations of a sphere of radius r at redshift z.
    
    error:
       An estimate of the numerical error on the calculated value of sigma.

    Notes:
    -----
    .. math:

    \sigma(R,z) = \sqrt{\int_0^\infty \frac{k^2}{2 \pi^2}~P(k, z)~
    \tilde{w}_k^2(k, R)~dk} = \sigma(R,0) \left(\frac{D_1(z)}{D_1(0)}\right)

    """
    omega_M_0 = cosmology['omega_M_0']
    
    fg = fgrowth(z, omega_M_0)

    if 'deltaSqr' not in cosmology:
        cosmology['deltaSqr'] = norm_power(**cosmology)
    
    #Uses 'n', as well as (for transfer_function_EH), 'omega_M_0',
    #'omega_b_0', 'omega_n_0', 'N_nu', 'omega_lambda_0', and 'h'.

    sigma_0_func = numpy.vectorize(_sigmasq_r_scalar)
    sigmasq_0, errorsq_0 = sigma_0_func(r,
                                        cosmology['n'],
                                        cosmology['deltaSqr'],
                                        cosmology['omega_M_0'],
                                        cosmology['omega_b_0'],
                                        cosmology['omega_n_0'],
                                        cosmology['N_nu'],
                                        cosmology['omega_lambda_0'],
                                        cosmology['h'],)
    sigma = numpy.sqrt(sigmasq_0) * fg

    # Propagate the error on sigmasq_0 to sigma.
    error = fg * errorsq_0 / (2. * sigmasq_0)

    return sigma, error

def norm_power(**cosmology):
    """Normalize the power spectrum to the specified sigma_8.

    Returns the factor deltaSqr.

    """
    cosmology['deltaSqr'] = 1.0
    deltaSqr = (cosmology['sigma_8'] / 
                sigma_r(8.0 / cosmology['h'], 0.0, **cosmology)[0] 
                )**2.0
    #print " deltaSqr = %.3g" % deltaSqr

    del cosmology['deltaSqr']
    sig8 = sigma_r(8.0 / cosmology['h'], 0.0, deltaSqr=deltaSqr, 
                   **cosmology)[0]
    #print " Input     sigma_8 = %.3g" % cosmology['sigma_8']
    #print " Numerical sigma_8 = %.3g" % sig8
    sigma_8_error = (sig8 - cosmology['sigma_8'])/cosmology['sigma_8']
    if sigma_8_error > 1e-4:
        warnings.warn("High sigma_8 fractional error = %.3g" % sigma_8_error)
    return deltaSqr

#def rho_crit(h):
#  return 3.0 * (h * H100)**2. / ( 8.0 * math.pi * G)

def power_spectrum(k, z, **cosmology):
    r"""Calculates the matter power spectrum P(k,z).

    Uses equation 25 of Eisenstein & Hu (1999 ApJ 511 5).

    Parameters:
    ----------
    
    k should be in Mpc^-1

    Cosmological Parameters:
    -----------------------
    
    Uses 'n', and either 'sigma_8' or 'deltaSqr', as well as, for
    transfer_function_EH, 'omega_M_0', 'omega_b_0', 'omega_n_0',
    'N_nu', 'omega_lambda_0', and 'h'.
    

    Notes:
    -----

    .. math:

    P(k,z) = \delta^2 \frac{2 \pi^2}{k^3} \left(\frac{c k}{h
    H_{100}}\right)^{3+n} \left(T(k,z) \frac{D_1(z)}{D_1(0)}\right)^2

    Using the non-dependence of the transfer function on redshift, we can
    rewrite this as

    .. math:

    P(k,z) = P(k,0) \left( \frac{D_1(z)}{D_1(0)} \right)^2

    which is used by sigma_r to the z-dependence out of the integral. 

    """

    omega_M_0 = cosmology['omega_M_0']
    n = cosmology['n']
    h = cosmology['h']
    if 'deltaSqr' in cosmology:
        deltaSqr = cosmology['deltaSqr']
    else:
        deltaSqr = norm_power(**cosmology)

    transFunc = transfer_function_EH(k, **cosmology)[0]

    # This equals D1(z)/D1(0)
    growthFact = fgrowth(z, omega_M_0)

    # Expression:
    # (sigma8/sig8)^2 * (2 pi^2) * k^-3. * (c * k / H_0)^(3 + n) * (tF * D)^2)

    # Simplifies to:
    # k^n (sigma8/sig8)^2 * (2 pi^2) * (c / H_0)^(3 + n) * (tF * D)^2

    # compare w/ icosmo:
    # k^n * tk^2 * (2 pi^2) * (sigma8/sig8)^2 * D^2
    # Just a different normalization.

    ps = (deltaSqr * (2. * math.pi**2.) * k**n *
          (cc.c_light_Mpc_s / (h * cc.H100_s))**(3. + n) * 
          (transFunc * growthFact)**2.)
    
    return ps 

def volume_radius_dmdr(mass, **cosmology):
    """Calculate volume, radius, and dm/dr for a sphere of the given mass.

    Uses the mean density of the universe.

    Parameters:
    ----------

    mass: array
       mass of the sphere in Solar Masses, M_sun. 

    Returns:
    -------

    volume in Mpc^3
    radius in Mpc
    dmdr in Msun / Mpc

    """
    rho_crit, rho_0 = cden.cosmo_densities(**cosmology)

    volume  = mass / rho_0
    r  = (volume / ((4. / 3.) * math.pi))**(1./3.)
    
    dmdr = 4. * math.pi * r**2. * rho_0

    return volume, r, dmdr

def mass_to_radius(mass, **cosmology):
    """Calculate the radius in Mpc of a sphere of the given mass.

    Parameters:
    -----------
    
    mass in Msun

    Returns:
    -------

    radius in Mpc

    Notes:
    -----

    This is a convenience function that calls volume_radius_dmdr and
    returns only the radius.
    
    """
    volume, r, dmdr = volume_radius_dmdr(mass, **cosmology)
    return r

def radius_to_mass(r, **cosmology):
    """Calculate the mass of a sphere of radius r in Mpc.

    Uses the mean density of the universe.

    """
    volume = (4./3.) * math.pi * r**3.
    
    if 'rho_0' in cosmology:
        rho_0 = cosmology['rho_0']
    else:
        rho_crit, rho_0 = cosmo_densities(**cosmology)

    mass = volume * rho_0
    return mass


def virial_temp(mass, z, mu=None, **cosmology):
    r"""Calculate the Virial temperature for a halo of a given mass.

    Calculate the Virial temperature in Kelvin for a halo of a given
    mass using equation 26 of Barkana & Loeb. 

    The transition from neutral to ionized is assumed to occur at temp
    = 1e4K. At temp >= 10^4 k, the mean partical mass drops from 1.22
    to 0.59 to very roughly account for collisional ionization.

    Parameters:
    ----------

    mass: array
       Mass in Solar Mass units.

    z: array
       Redshift.

    mu: array, optional
       Mean mass per particle.

    """

    omega_M_0 = cosmology['omega_M_0']
    omega = cden.omega_M_z(z, **cosmology)
    d = omega - 1
    deltac = 18. * math.pi**2. + 82. * d - 39. * d**2.

    if mu is None:
        mu_t = 1.22
    else:
        mu_t = mu
    temp = (1.98e4 * 
            (mass * cosmology['h']/1.0e8)**(2.0/3.0) * 
            (omega_M_0 * deltac / (omega * 18. * math.pi**2.))**(1.0/3.0) * 
            ((1 + z) / 10.0) * 
            (mu_t / 0.6))

    if mu is None:
        # Below is some magic to consistently use mu = 1.22 at temp < 1e4K
        # and mu = 0.59 at temp >= 1e4K.
        t_crit = 1e4
        t_crit_large = 1.22 * t_crit / 0.6
        t_crit_small = t_crit
        mu = ((temp < t_crit_small) * 1.22 + 
              (temp > t_crit_large) * 0.59 +
              (1e4 * 1.22/temp) * 
              (temp >= t_crit_small) * (temp <= t_crit_large))
        temp = temp * mu / 1.22
        
    return temp

def virial_mass(temp, z, **cosmology):
    r"""Calculate the mass of a halo of the given Virial temperature.

    Uses equation 26 of Barkana & Loeb (2001PhR...349..125B), solved
    for T_vir as a function of mass.

    Parameters:
    ----------
    
    temp: array
       Virial temperature of the halo in Kelvin.

    z: array
       Redshift.

    Returns:
    -------
    
    mass: array
       The mass of such a halo in Solar Masses.

    Notes:
    -----

    At temp >= 10^4 k, the mean partical mass drops from 1.22 to 0.59
    to very roughly account for collisional ionization.

    Examples:
    --------

    >>> cosmo = {'omega_M_0' : 0.27, 
    ...          'omega_lambda_0' : 1-0.27, 
    ...          'omega_b_0' : 0.045, 
    ...          'omega_n_0' : 0.0,
    ...          'N_nu' : 0,
    ...          'h' : 0.72,
    ...          'n' : 1.0,
    ...          'sigma_8' : 0.9
    ...          } 
    >>> mass = virial_mass(1e4, 6.0, **cosmo)
    >>> temp = virial_temp(mass, 6.0, **cosmo)
    >>> print "Mass = %.3g M_sun" % mass
    Mass = 1.68e+08 M_sun
    >>> print round(temp, 4)
    10000.0

    """
    t_crit = 1e4
    mu = (temp < t_crit) * 1.22 + (temp >= t_crit) * 0.59
    
    divisor = virial_temp(1.0e8 / cosmology['h'], z, mu=mu, **cosmology)
    return 1.0e8 * (temp/divisor)**(3.0/2.0) / cosmology['h'];

def sig_del(temp_min, z, mass=None, passed_min_mass = False, **cosmology):
    """Convenience function to calculate collapse fraction inputs.

    Parameters:
    ----------

    temp_min:
       Minimum Virial temperature for a halo to be counted. Or minimum
       mass, if passed_min_mass is True.

    z:
       Redshift.

    mass: optional
       The mass of the region under consideration. Defaults to
       considering the entire universe.

    passed_min_mass: boolean
       Indicates that the first argument is actually the minimum mass,
       not the minimum Virial temperature.

    """

    if passed_min_mass:
        mass_min = temp_min
    else:
        mass_min = virial_mass(temp_min, z, **cosmology)
    r_min = mass_to_radius(mass_min, **cosmology) 
    sigma_min = sigma_r(r_min, 0., **cosmology)
    sigma_min = sigma_min[0]

    fg = fgrowth(z, cosmology['omega_M_0'])
    delta_c = 1.686 / fg

    if mass is None:
        return sigma_min, delta_c
    else:
        r_mass = mass_to_radius(mass) 
        sigma_mass = sigma_r(r_mass, 0., **cosmology)
        return sigma_min, delta_c, sigma_mass

def collapse_fraction(sigma_min, delta_crit, sigma_mass=0, delta=0):
    r"""Fraction of mass contained in collapsed objects.

    Use sig_del to conveniently obtain sigma_min and delta_crit. See
    Examples velow.

    Parameters:
    ----------

    sigma_min: 
       The standard deviatiation of density fluctuations on the scale
       corresponding to the minimum mass for a halo to be counted.

    delta_crit:
       The critical (over)density of collapse.

    sigma_mass:
       The standard deviation of density fluctuations on the scale
       corresponding to the mass of the region under
       consideration. Use zero to consider the entire universe.

    delta: 
       The overdensity of the region under consideration. Zero
       corresponds to the mean density of the universe.

    Notes:
    -----

    The fraction of the mass in a region of mass m that has already
    collapsed into halos above mass m_min is:

    .. math:

    f_\mathrm{col} = \mathrm{erfc} \left[ \frac{\delta_c - \delta(m)}
    { \sqrt {2 [\sigma^2(m_\mathrm{min}) - \sigma^2(m)]}} \right]

    
    The answer isn't real if sigma_mass > sigma_min.

    Note that there is a slight inconsistency in the mass used to
    calculate sigma in the above formula, since the region deviates
    from the average density.

    Examples:
    -----

    >>> import numpy
    >>> import perturbation as cp
    >>> cosmo = {'omega_M_0' : 0.27, 
    ...          'omega_lambda_0' : 1-0.27, 
    ...          'omega_b_0' : 0.045, 
    ...          'omega_n_0' : 0.0,
    ...          'N_nu' : 0,
    ...          'h' : 0.72,
    ...          'n' : 1.0,
    ...          'sigma_8' : 0.9
    ...          } 
    >>> fc = cp.collapse_fraction(*cp.sig_del(1e4, 0, **cosmo))
    >>> print round(fc, 4)
    0.7328
    >>> fc = cp.collapse_fraction(*cp.sig_del(1e2, 0, **cosmo))
    >>> print round(fc, 4)
    0.8571
    
    """

    fraction = scipy.special.erfc((delta_crit - delta) / 
                                  (numpy.sqrt(2. * 
                                              (sigma_min**2. - sigma_mass**2.)
                                              )
                                   ))
    return fraction

if __name__ == "__main__":
    import doctest
    doctest.testmod()