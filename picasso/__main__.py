#!/usr/bin/env python
"""
    picasso.__main__.py
    ~~~~~~~~~~~~~~~~

    Picasso command line interface

    :author: Joerg Schnitzbauer, 2015
"""


import sys
import os.path

_this_file = os.path.abspath(__file__)
_this_directory = os.path.dirname(_this_file)
_parent_directory = os.path.dirname(_this_directory)
sys.path.insert(0, _parent_directory)    # We want to use the local picasso instead the system-wide


def _link(files, min_prob, tolerance):
    import glob
    paths = glob.glob(files)
    if paths:
        from picasso import io, postprocess
        for path in paths:
            locs, info = io.load_locs(path)
            linked_locs = postprocess.link(locs, min_prob, tolerance)
            base, ext = os.path.splitext(path)
            link_info = {'Minimum Probablity': min_prob,
                         'Maximum Transient Dark Time': tolerance,
                         'Generated by': 'Picasso Link'}
            info.append(link_info)
            io.save_locs(base + '_link.hdf5', linked_locs, info)


def _undrift(files, mode, segmentation, display, fromfile):
    import glob
    paths = glob.glob(files)
    if paths:
        from picasso import io
        from numpy import savetxt
        if fromfile is not None:
            from numpy import genfromtxt
            drift = genfromtxt(fromfile)
            for path in paths:
                locs, info = io.load_locs(path)
                locs.x -= drift[:, 1][locs.frame]
                locs.y -= drift[:, 0][locs.frame]
                undrift_info = {'From File': fromfile,
                                'Generated by': 'Picasso Undrift'}
                info.append(undrift_info)
                base, ext = os.path.splitext(path)
                io.save_locs(base + '_undrift.hdf5', locs, info)
                savetxt(base + '_drift.txt', drift, header='dx\tdy', newline='\r\n')
                if display:
                    import matplotlib.pyplot as plt
                    plt.style.use('ggplot')
                    plt.figure(figsize=(17, 6))
                    plt.suptitle('Estimated drift')
                    plt.subplot(1, 2, 1)
                    plt.plot(drift[:, 1], label='x')
                    plt.plot(drift[:, 0], label='y')
                    plt.legend(loc='best')
                    plt.xlabel('Frame')
                    plt.ylabel('Drift (pixel)')
                    plt.subplot(1, 2, 2)
                    plt.plot(drift[:, 1], drift[:, 0], color=list(plt.rcParams['axes.prop_cycle'])[2]['color'])
                    plt.axis('equal')
                    plt.xlabel('x')
                    plt.ylabel('y')
                    plt.show()
        else:
            from picasso import postprocess
            for path in paths:
                print('Undrifting file {}'.format(path))
                locs, info = io.load_locs(path)
                movie = None
                if mode == 'std':
                    directory = os.path.dirname(os.path.abspath(path))
                    movie, _ = io.load_raw(os.path.join(directory, info[0]['Raw File']))
                drift, locs = postprocess.undrift(locs, info, segmentation, mode=mode, movie=movie, display=display)
                base, ext = os.path.splitext(path)
                undrift_info = {'Mode': mode,
                                'Display': display,
                                'Generated by': 'Picasso Undrift'}
                if mode in ['render', 'std']:
                    undrift_info['Segmentation'] = segmentation
                info.append(undrift_info)
                io.save_locs(base + '_undrift.hdf5', locs, info)
                savetxt(base + '_drift.txt', drift, header='dx\tdy', newline='\r\n')


def _density(files, radius):
    import glob
    paths = glob.glob(files)
    if paths:
        from picasso import io, postprocess
        for path in paths:
            locs, info = io.load_locs(path)
            locs = postprocess.compute_local_density(locs, info, radius)
            base, ext = os.path.splitext(path)
            density_info = {'Generated by': 'Picasso Density',
                            'Radius': radius}
            info.append(density_info)
            io.save_locs(base + '_density.hdf5', locs, info)


def _dbscan(files, radius, min_density):
    import glob
    paths = glob.glob(files)
    if paths:
        from picasso import io, postprocess
        from h5py import File
        for path in paths:
            print('Loading {} ...'.format(path))
            locs, info = io.load_locs(path)
            clusters, locs = postprocess.dbscan(locs, radius, min_density)
            base, ext = os.path.splitext(path)
            dbscan_info = {'Generated by': 'Picasso DBSCAN',
                           'Radius': radius,
                           'Minimum local density': min_density}
            info.append(dbscan_info)
            io.save_locs(base + '_dbscan.hdf5', locs, info)
            with File(base + '_clusters.hdf5', 'w') as clusters_file:
                clusters_file.create_dataset('clusters', data=clusters)


def _dark(files):
    import glob
    paths = glob.glob(files)
    if paths:
        from picasso import io, postprocess
        for path in paths:
            locs, info = io.load_locs(path)
            locs = postprocess.compute_dark_times(locs)
            base, ext = os.path.splitext(path)
            dbscan_info = {'Generated by': 'Picasso Dark'}
            info.append(dbscan_info)
            io.save_locs(base + '_dark.hdf5', locs, info)


def _std(files):
    import glob
    paths = glob.glob(files)
    if paths:
        from picasso.io import load_raw
        from numpy import std
        from os.path import splitext
        from tifffile import imsave
        for path in paths:
            movie, info = load_raw(path)
            std_image = std(movie, axis=0, dtype='f4')
            base, ext = splitext(path)
            imsave(base + '_std.tif', std_image)


def _align(target, file, affine, display):
    from picasso.io import load_locs, save_locs
    from picasso.postprocess import align
    from os.path import splitext
    target_locs, target_info = load_locs(target)
    locs, info = load_locs(file)
    aligned_locs = align(target_locs, target_info, locs, info, affine=affine, display=display)
    align_info = {'Generated by': 'Picasso Align',
                  'Target': target}
    info.append(align_info)
    base, ext = splitext(file)
    save_locs(base + '_align.hdf5', aligned_locs, info)


def _join(files):
    from picasso.io import load_locs, save_locs
    from os.path import splitext
    from numpy import append
    locs, info = load_locs(files[0])
    join_info = {'Generated by': 'Picasso Join',
                 'Files': [files[0]]}
    for path in files[1:]:
        locs_, info_ = load_locs(path)
        locs = append(locs, locs_)
        join_info['Files'].append(path)
    base, ext = splitext(files[0])
    info.append(join_info)
    locs.sort(kind='mergesort', order='frame')
    save_locs(base + '_join.hdf5', locs, info)


def _kinetics(path, ignore):
    from picasso.io import load_locs
    locs, info = load_locs(path)
    from picasso.lib import calculate_optimal_bins
    from numpy import histogram
    from lmfit.models import ExponentialModel
    from matplotlib.pyplot import show
    from matplotlib.pyplot import style
    style.use('ggplot')
    if hasattr(locs, 'len'):
        print('~~~ LENGTH ~~~')
        bin_len = calculate_optimal_bins(locs.len)
        hist_len, bin_len_edges = histogram(locs.len, bin_len)
        bin_centers = bin_len_edges[:-1] + bin_len_edges[1] / 2
        model = ExponentialModel()
        parameters = model.guess(hist_len[ignore:], x=bin_centers[ignore:])
        res = model.fit(hist_len[ignore:], parameters, x=bin_centers[ignore:])
        print(res.fit_report())
        res.plot()
        show()
    if hasattr(locs, 'dark'):
        print('~~~ DARK ~~~')
        bin_dark = calculate_optimal_bins(locs.dark)
        hist_dark, bin_dark_edges = histogram(locs.dark, bin_dark)
        bin_centers = bin_dark_edges[:-1] + bin_dark_edges[1] / 2
        model = ExponentialModel()
        parameters = model.guess(hist_dark[ignore:], x=bin_centers[ignore:])
        res = model.fit(hist_dark[ignore:], parameters, x=bin_centers[ignore:])
        print(res.fit_report())
        res.plot()
        show()


def _pair_correlation(files, bin_size, r_max):
    from glob import glob
    paths = glob(files)
    if paths:
        from picasso.io import load_locs
        from picasso.postprocess import pair_correlation
        from matplotlib.pyplot import plot, style, show, xlabel, ylabel
        style.use('ggplot')
        for path in paths:
            print('Loading {}...'.format(path))
            locs, info = load_locs(path)
            print('Calculating pair-correlation...')
            bins_lower, pc = pair_correlation(locs, info, bin_size, r_max)
            plot(bins_lower, pc)
            xlabel('r (pixel)')
            ylabel('pair-correlation (pixel^-2)')
            show()


if __name__ == '__main__':
    import argparse

    # Main parser
    parser = argparse.ArgumentParser('picasso')
    subparsers = parser.add_subparsers(dest='command')

    # toraw parser
    toraw_parser = subparsers.add_parser('toraw', help='convert image sequences to binary raw files and accompanied YAML information files')
    toraw_parser.add_argument('files', help='one or multiple files specified by a unix style pathname pattern')

    # link parser
    link_parser = subparsers.add_parser('link', help='link localizations in consecutive frames')
    link_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    link_parser.add_argument('-p', '--probability', type=float, default=0.05,
                             help='minimum probablity that two localizations are the same event based on their localization precisions (default=0.05)')
    link_parser.add_argument('-t', '--tolerance', type=int, default=1,
                             help='maximum dark time between localizations to still consider them the same binding event (default=1)')

    # undrift parser
    undrift_parser = subparsers.add_parser('undrift', help='correct localization coordinates for drift')
    undrift_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    undrift_parser.add_argument('-m', '--mode', default='render', help='"std", "render" or "framepair")')
    undrift_parser.add_argument('-s', '--segmentation', type=float, default=1000,
                                help='the number of frames to be combined for one temporal segment (default=1000)')
    undrift_parser.add_argument('-f', '--fromfile', type=str, help='apply drift from specified file instead of computing it')
    undrift_parser.add_argument('-d', '--nodisplay', action='store_false', help='do not display estimated drift')

    # local density
    density_parser = subparsers.add_parser('density', help='compute the local density of localizations')
    density_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    density_parser.add_argument('radius', type=float, help='maximal distance between to localizations to be considered local')

    # DBSCAN
    dbscan_parser = subparsers.add_parser('dbscan', help='cluster localizations')
    dbscan_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    dbscan_parser.add_argument('radius', type=float, help='maximal distance between to localizations to be considered local')
    dbscan_parser.add_argument('density', type=int, help='minimum local density for localizations to be assigned to a cluster')

    # Dark time
    dark_parser = subparsers.add_parser('dark', help='compute the dark time for grouped localizations')
    dark_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    # STD Image
    std_parser = subparsers.add_parser('std', help='generate the std image of a raw movie')
    std_parser.add_argument('files', help='one or multiple raw files, specified by a unix style path pattern')

    # align
    align_parser = subparsers.add_parser('align', help='align one localization file to another')
    align_parser.add_argument('-d', '--display', help='display correlation', action='store_true')
    align_parser.add_argument('-a', '--affine', help='include affine transformations', action='store_true')
    align_parser.add_argument('target', help='the file to which the other should be aligned')
    align_parser.add_argument('file', help='the file to be aligned to the target file')

    # join
    join_parser = subparsers.add_parser('join', help='join hdf5 localization lists')
    join_parser.add_argument('file', nargs='+', help='the hdf5 localization files to be joined')

    # kinetics
    kinetics_parser = subparsers.add_parser('kinetics', help='calculate and display binding kinetics')
    kinetics_parser.add_argument('-i', '--ignore', type=int, default=1, help='the number of bins to be ignored for short kinetic events')
    kinetics_parser.add_argument('file', help='the hdf5 localization file to be analyzed')

    # Pair correlation
    pc_parser = subparsers.add_parser('pc', help='calculate the pair-correlation of localizations')
    pc_parser.add_argument('-b', '--binsize', type=float, default=0.1, help='the bin size')
    pc_parser.add_argument('-r', '--rmax', type=float, default=10, help='The maximum distance to calculate the pair-correlation')
    pc_parser.add_argument('files', help='one or multiple hdf5 localization files')

    # Parse
    args = parser.parse_args()
    if args.command:
        if args.command == 'toraw':
            from picasso import io
            io.to_raw(args.files, verbose=True)
        elif args.command == 'link':
            _link(args.files, args.probability, args.tolerance)
        elif args.command == 'undrift':
            _undrift(args.files, args.mode, args.segmentation, args.nodisplay, args.fromfile)
        elif args.command == 'density':
            _density(args.files, args.radius)
        elif args.command == 'dbscan':
            _dbscan(args.files, args.radius, args.density)
        elif args.command == 'dark':
            _dark(args.files)
        elif args.command == 'std':
            _std(args.files)
        elif args.command == 'align':
            _align(args.target, args.file, args.affine, args.display)
        elif args.command == 'join':
            _join(args.file)
        elif args.command == 'kinetics':
            _kinetics(args.file, args.ignore)
        elif args.command == 'pc':
            _pair_correlation(args.files, args.binsize, args.rmax)
    else:
        parser.print_help()
