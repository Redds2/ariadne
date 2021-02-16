import torch
import numpy as np
import itertools
import pandas as pd
from copy import deepcopy
from ariadne.tracknet_v2.metrics import point_in_ellipse
import faiss
import matplotlib.pyplot as plt
from scipy.interpolate import make_interp_spline, BSpline
import os

def fix_random_seed(seed):
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.deterministic = True #torch.backends.cudnn.determenistic
        torch.benchmark = False #torch.backends.cudnn.benchmark

def cartesian(df1, df2):
    rows = itertools.product(df1.iterrows(), df2.iterrows())
    df = pd.DataFrame(left.append(right) for (_, left), (_, right) in rows)
    df_fakes = df[(df['track_left'] == -1) & (df['track_right'] == -1)]
    df = df[(df['track_left'] != df['track_right'])]
    df = pd.concat([df, df_fakes], axis=0)
    df = df.sample(frac=1).reset_index(drop=True)
    return df.reset_index(drop=True)

def weights_update(model, checkpoint):
    model_dict = model.state_dict()
    pretrained_dict = checkpoint['state_dict']
    real_dict = {}
    for (k, v) in model_dict.items():
        needed_key = None
        for pretr_key in pretrained_dict:
            if k in pretr_key:
                needed_key = pretr_key
                break
        assert needed_key is not None, "key %s not in pretrained_dict %r!" % (k, pretrained_dict.keys())
        real_dict[k] = pretrained_dict[needed_key]

    model.load_state_dict(real_dict)
    model.eval()
    return model

def find_nearest_hit_no_faiss(ellipses, y, return_numpy=False):
    centers = ellipses[:, :2]
    last_station_hits = deepcopy(y)
    dists = torch.cdist(last_station_hits.float(), centers.float())
    minimal = last_station_hits[torch.argmin(dists, dim=0)]
    is_in_ellipse = point_in_ellipse(ellipses, minimal)
    if return_numpy:
        minimal = minimal.detach().cpu().numpy()
        is_in_ellipse  = is_in_ellipse.detach().cpu().numpy()
    return minimal, is_in_ellipse

def find_nearest_hit(ellipses, last_station_hits):
    #numpy, numpy -> numpy, numpy
    index = faiss.IndexFlatL2(2)
    index.add(last_station_hits.astype('float32'))
    #ellipses = torch_ellipses.detach().cpu().numpy()
    centers = ellipses[:,:2]
    d, i = index.search(np.ascontiguousarray(centers.astype('float32')), 1)
    x_part = d.flatten() / ellipses[:, 2].flatten()**2
    y_part = d.flatten() / ellipses[:, 3].flatten()**2
    left_side = x_part + y_part
    is_in_ellipse = left_side <= 1
    return last_station_hits[i.flatten()], is_in_ellipse

def get_diagram_arr_linspace(all_real_hits, found_hits, start, end, num, col):
    spac = np.linspace(start, end, num=num)

    arr = []

    for i in range(len(spac) - 1):
        beg = spac[i]
        end = spac[i + 1]
        elems_real = all_real_hits[(all_real_hits[col] > beg) & (all_real_hits[col] < end)]
        elems_pred = found_hits[(found_hits[col] > beg) & (found_hits[col] < end)]
        if elems_real.empty:
            arr.append(np.NaN)
            continue
        arr.append(len(elems_pred) / len(elems_real))

    return arr, spac[:-1]

def draw_for_col(tracks_real, tracks_pred_true,
                 col, col_pretty, total_events, n_ticks=150, n_boxes=10, model_name='TrackNETV2.1', style='boxplot'):

    start = tracks_real[tracks_real[col] > -np.inf][col].min()
    end = tracks_real[tracks_real[col] < np.inf][col].max()

    initial, spac = get_diagram_arr_linspace(tracks_real, tracks_pred_true, start, end, n_ticks, col)
    # mean line
    # find number of ticks until no nans present

    if style == 'boxplot':
        interval_size = len(initial) / n_boxes
        subarrays = {}
        positions = {}
        means = {}
        stds = {}
        first = 0
        #get_boxes
        for interval in range(n_boxes):
            second = int(first + interval_size)
            values_in_interval = initial[first:min(second, len(initial))]
            pos_in_interval = spac[first:min(second, len(initial))]
            means[interval] = np.mean(values_in_interval)
            stds[interval] = np.std(values_in_interval)
            positions[interval] = np.mean(pos_in_interval)
            first = second
        draw_from_data(title=f'{model_name} track efficiency vs {col_pretty} ({total_events} events)',
                       data_x=list(positions.values()),
                       data_y=list(means.values()),
                       data_y_err=list(stds.values()),
                       axis_x=col_pretty)
    elif style=='plot':
        second = np.array([np.nan])
        count_start = n_ticks // 5
        while np.isnan(second).any():
            second, spac2 = get_diagram_arr_linspace(tracks_real, tracks_pred_true, start, end, count_start, col)
            count_start = count_start - count_start // 2
        xnew = np.linspace(spac2.min(), spac2.max(), count_start)
        spl = make_interp_spline(spac2, second, k=3)  # type: BSpline
        power_smooth = spl(xnew)
        maxX = end
        plt.figure(figsize=(8, 7))
        plt.subplot(111)
        plt.ylabel('Track efficiency', fontsize=12)
        plt.xlabel(col_pretty, fontsize=12)
        # plt.axis([0, maxX, 0, 1.005])
        plt.plot(spac, initial, alpha=0.8, lw=0.8)
        plt.title(f'{model_name} track efficiency vs {col_pretty} ({total_events} events)', fontsize=14)
        plt.plot(xnew, power_smooth, ls='--', label='mean', lw=2.5)
        plt.xticks(np.linspace(start, maxX, 8))
        plt.yticks(np.linspace(0, 1, 9))
        plt.legend(loc=0)
        plt.grid()
        plt.tight_layout()
        plt.rcParams['savefig.facecolor'] = 'white'
        os.makedirs('../output', exist_ok=True)
        plt.savefig(f'../output/{model_name}_img_track_eff_{col}_ev{total_events}_t{n_ticks}.png', dpi=300)
        plt.show()
    else:
        raise NotImplementedError(f"Style of plotting '{style}' is not supported yet")

def boxplot_style_data(bp):
    for box in bp['boxes']:
        # change outline color
        # box.set( color='#7570b3', linewidth=2)
        # change fill color
        box.set(facecolor='silver')

    ## change color and linewidth of the whiskers
    # for whisker in bp['whiskers']:
    #    whisker.set(color='#7570b3', linewidth=2)
    #
    ### change color and linewidth of the caps
    # for cap in bp['caps']:
    #    cap.set(color='#7570b3', linewidth=2)
    #
    ### change color and linewidth of the medians
    for median in bp['medians']:
        median.set(color='tab:cyan', linewidth=3, alpha=0)

    for median in bp['means']:
        median.set(color='tab:green', linewidth=4, ls='-', zorder=5)
    #
    ### change the style of fliers and their fill
    # for flier in bp['fliers']:
    #    flier.set(marker='o', color='#e7298a', alpha=0.5)


def draw_from_data(title, data_x, data_y, data_y_err, axis_x=None, axis_y=None, model_name='tracknet', **kwargs):
    data_x = np.array(data_x)
    data_y_init = np.array(data_y)
    dataep = data_y + np.array(data_y_err)
    dataem = data_y - np.array(data_y_err)

    data_y = np.expand_dims(data_y, axis=-1)
    dataep = np.expand_dims(dataep, axis=-1)
    dataem = np.expand_dims(dataem, axis=-1)

    data_y = np.concatenate((data_y, dataep, dataem), axis=1).T

    plt.figure(figsize=(8, 7))

    ax = plt.subplot(111)

    plt.title(title, fontsize=14)
    plt.locator_params(axis='x', nbins=len(data_x) + 1)
    delta_x = (data_x[1] - data_x[0]) / 2
    bp = plt.boxplot(data_y, positions=data_x,
                     manage_ticks=False, meanline=True, showmeans=True,
                     widths=delta_x, patch_artist=True, sym='', zorder=3)

    xnew = np.linspace(data_x.min(), data_x.max(), len(data_x))
    if axis_x:
        plt.xlabel(axis_x, fontsize=12)
    if axis_y:
        plt.ylabel(axis_y, fontsize=12)
    mean_data = data_y_init
    spl = make_interp_spline(data_x, mean_data, k=1)  # type: BSpline
    power_smooth = spl(xnew)
    if 'mean_label' in kwargs:
        label = kwargs['mean_label']
    else:
        label = 'mean efficiency'
    plt.plot(xnew, power_smooth, ls='--', color='tab:orange', label=label, lw=3, zorder=4)

    boxplot_style_data(bp)
    ax.grid()
    ax.legend(loc=0)
    if data_y.max() < 1.1:
        plt.yticks(np.round(np.linspace(0, 1, 11), decimals=2))
    if 'scale' in kwargs:
        plt.yscale(kwargs['scale'])
    plt.tight_layout()
    plt.rcParams['savefig.facecolor'] = 'white'
    os.makedirs('../output', exist_ok=True)
    plt.savefig(f'../output/{model_name}_{title.lower().replace(" ", "_").replace(".","_")}.png', dpi=300)
    plt.show()
