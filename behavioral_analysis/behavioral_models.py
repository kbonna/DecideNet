import numpy as np

def estimate_values(beh, meta, subject, condition, alpha):
    '''Implements TD learning model on experienced probabilistic outcomes.

    Args:
        beh (np.array): aggregated behavioral responses
        meta (dict): description of beh array coding
        subject (int): subject index
        condition (int): task condition index
        alpha (float): learning rate

    Returns:
        val (np.array): reflects algorithm trialwise beliefs about
            probabilities that box will be rewarded / punished
    '''

    val = np.zeros((beh.shape[2], 2))
    val[0] = [.5, .5] # Initial beliefs (agnostic)

    rewarded = beh[subject, condition, :, meta['dim4'].index('rwd')][:-1]

    for trial, rwd in enumerate(rewarded):
        val[trial+1, 1] = val[trial, 1] + alpha * ((rwd + 1)/2 - val[trial, 1])
        val[trial+1, 0] = val[trial, 0] + alpha * ((-rwd + 1)/2 - val[trial, 0])

    return val

def estimate_utilities(beh, meta, subject, condition, gamma=1, delta=1):
    '''Implements function converting reward magnitude to experienced utility.

    Args:
        beh (np.array): aggregated behavioral responses
        meta (dict): description of beh array coding
        subject (int): subject index
        condition (int): task condition index
        gamma (float): loss aversion parameter
        delta: (float): risk aversion parameter

    Returns:
        util (np.array): reflects algorithm trialwise estimates of utility
            for both left and right boxes
    '''
    util = np.zeros((beh.shape[2], 2))

    if condition == meta['dim2'].index('pun'):
        factor = (-1) * gamma
    else:
        factor = 1

    util[:, 0] = factor * np.power(
        np.abs(beh[subject, condition, :, meta['dim4'].index('magn_left')]),
        delta
    )
    util[:, 1] = factor * np.power(
        np.abs(beh[subject, condition, :, meta['dim4'].index('magn_right')]),
        delta
    )

    return util

def estimate_choice_probability(val, util, kind='simple', theta=None):
    '''Implements softmax decision rule reflecting choice probabilities

    Args:
        val (np.array): trialwise beliefs about probabilities that box will
            be rewarded / punished
        util (np.array): trialwise estimates of utility for both boxes
        kind (str): either 'simple' or 'softmax' for two different models
        theta (float): inverse temperature for softmax function

    Returns:
        p (np.array): trialwise choice probabilities
    '''

    # Calculate expected value for both options
    ev = np.multiply(util, val)

    if kind == 'simple':
        p = ev / np.sum(ev, axis=1)[:, np.newaxis]
        if np.sum(ev) < 0:
            p = np.fliplr(p)

    elif kind == 'softmax':
        p = np.exp(theta * ev) / np.sum(np.exp(theta * ev), axis=1)[:, np.newaxis]

    return p

def g_square(beh, meta, subject, condition, p):
    '''Calculate badness-of-fit quality measure. G-square is inversely
    related to log likelyhood.

    Args:
        beh (np.array): aggregated behavioral responses
        meta (dict): description of beh array coding
        subject (int): subject index
        condition (int): task condition index
        p (np.array): trialwise choice probabilities

    Returns:
        (float): g-square badness-of-fit
    '''

    ll = 0
    responses = beh[subject, condition, :, meta['dim4'].index('response')]

    for trial, response in enumerate(responses):
        if response == -1:
            ll += np.log(p[trial, 0])
        elif response == 1:
            ll += np.log(p[trial, 1])

    return (-2) * ll

### Behavioral Models #######################################################
def model1(beh, meta, subject, condition, alpha):
    '''Simple one-parameter model with variable learning rate.'''

    val = estimate_values(beh, meta, subject, condition, alpha)
    util = estimate_utilities(beh, meta, subject, condition)
    p = estimate_choice_probability(val, util, kind='simple')

    return (val, util, p)


def model2(beh, meta, subject, condition, alpha, theta):
    '''Two-parameter model  with variable learning rate and inverse T.'''

    val = estimate_values(beh, meta, subject, condition, alpha)
    util = estimate_utilities(beh, meta, subject, condition)
    p = estimate_choice_probability(val, util, kind='softmax', theta=theta)

    return (val, util, p)

def model3(beh, meta, subject, condition, alpha, theta, gamma, delta):
    '''Four-parameter model.

    Args:
        alpha (float): learning rate
        theta (float): inverse softmax temperature
        gamma (float): loss aversion
        delta (float): risk aversion
    '''

    val = estimate_values(beh, meta, subject, condition, alpha)
    util = estimate_utilities(beh, meta, subject, condition, gamma, delta)
    p = estimate_choice_probability(val, util, kind='softmax', theta=theta)

    return (val, util, p)
