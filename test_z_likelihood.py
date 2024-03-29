import numpy as np
import hawkes as hwk
import likelihood_utils
from scipy.stats import expon
from sklearn.metrics import f1_score, auc, roc_curve
from hawkes_uncertain_simulator import HawkesUncertainModel

plot_base_path = '/shared/Results/HawkesUncertainEvents/temp'

_h_intensity = 0.9
_h_beta = 2
_h_alpha = 1.1

_runtime = 30

_p_intensity = 0.3

_h_exp_rate = 3.5
_p_exp_rate = 2.5

hum = HawkesUncertainModel(h_lambda=_h_intensity, h_alpha=_h_alpha, h_beta=_h_beta, h_exp_rate=_h_exp_rate,
                           p_lambda=_p_intensity, p_exp_rate=_p_exp_rate,
                           noise_percentage_ub=0.2, run_time=_runtime, delta=0.01, seed=3)

print("Noise Percentage: ", hum.noise_percentage)


# Testing out the prob of the full posterior
sim_event_times = hum.mixed_timestamps
sim_event_marks = hum.mixed_expo
sim_true_labels = hum.mixed_labels.astype(np.bool)
sim_true_z_prior = hum.noise_percentage

print("Z Posterior Prob: ", likelihood_utils.z_posterior_prob(sim_true_labels, sim_event_times, sim_event_marks,
                                                              sim_true_z_prior, (_h_intensity, _h_alpha, _h_beta),
                                                              _p_intensity, _h_exp_rate, _p_exp_rate))

print("Z Posterior Log Prob: ", likelihood_utils.z_posterior_log_prob(sim_true_labels, sim_event_times, sim_event_marks,
                                                                      sim_true_z_prior,
                                                                      (_h_intensity, _h_alpha, _h_beta),
                                                                      _p_intensity, _h_exp_rate, _p_exp_rate))


def sample_z(events_t, events_info,
             hw_sample_alpha, hw_sample_beta, hw_sample_intensity,
             poi_sample_intensity,
             exp_hw_sample_rate, exp_poi_sample_rate,
             hawkes_cat_prob):

    num_events = len(events_t)

    event_assignment = np.zeros(num_events, dtype=int)
    mixture_log_prob = np.zeros((num_events, 2))

    # The order of likelihoods are switched here to accommodate the hawkes mask
    # compute log_prob of cat assignment, due to the exp mixture model
    exp_hawkes_log_prob = expon.logpdf(events_info, loc=0, scale=1. / exp_hw_sample_rate)
    exp_poisson_log_prob = expon.logpdf(events_info, loc=0, scale=1. / exp_poi_sample_rate)
    exp_log_prob = np.stack((exp_poisson_log_prob, exp_hawkes_log_prob), axis=-1)

    stacked_cat_probs = np.log(np.array([1. - hawkes_cat_prob, hawkes_cat_prob]))

    exp_mixture_log_prob = stacked_cat_probs + exp_log_prob
    # exp_mixture_log_prob = exp_log_prob

    pp_mixture_log_prob = np.zeros((num_events, 2))
    hawkes_mask = np.zeros(num_events, dtype=int)
    last_noise_timestamp = 0

    for i in range(num_events):
        hawkes_times = np.append(events_t[hawkes_mask == 1], events_t[i])
        hawkes_ll = likelihood_utils.hawkes_log_likelihood_numpy(hawkes_times, hw_sample_intensity, hw_sample_alpha,
                                                                 hw_sample_beta)

        # poisson log-likelihood
        poisson_ll = expon.logcdf(events_t[i] - last_noise_timestamp, loc=0, scale=1. / poi_sample_intensity)

        # poisson_times = np.append(events_t[event_assignment == 1], events_t[i])
        # poisson_interarrivals = poisson_times[1:] - poisson_times[:-1]
        # poisson_interarrivals = np.insert(poisson_interarrivals, 0, poisson_times[0])
        # poisson_ll = np.sum(expon.logpdf(poisson_interarrivals, loc=0, scale=1. / poi_sample_intensity))

        pp_mixture_log_prob[i] = [poisson_ll, hawkes_ll]

        # All prob
        mixture_log_prob[i] = exp_mixture_log_prob[i] + pp_mixture_log_prob[i]

        # exp mixture only
        # mixture_log_prob[i] = exp_mixture_log_prob[i]

        # pp mixture only
        # mixture_log_prob[i] = pp_mixture_log_prob[i]

        event_assignment[i] = np.abs(np.argmax(mixture_log_prob[i]) - 1)
        hawkes_mask[i] = np.argmax(mixture_log_prob[i])

        if event_assignment[i] == 0:
            last_noise_timestamp = events_t[i]

    return event_assignment, mixture_log_prob


event_assignment, mixture_log_prob = sample_z(hum.mixed_timestamps, hum.mixed_expo,
                                              _h_alpha, _h_beta, _h_intensity,
                                              _p_intensity,
                                              _h_exp_rate, _p_exp_rate,
                                              1 - hum.noise_percentage)

print(mixture_log_prob)
print("y_pred:", event_assignment)
print("y_true:", hum.mixed_labels)

if np.sum(event_assignment) != 0 and np.sum(event_assignment) != len(event_assignment):
    print("f1:", f1_score(hum.mixed_labels, event_assignment))

probs = np.exp(mixture_log_prob[:, 0]) / np.sum(np.exp(mixture_log_prob), axis=1)
fpr, tpr, thresholds = roc_curve(hum.mixed_labels, probs)
print("AUC:", auc(fpr, tpr))
