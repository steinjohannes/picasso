#!/usr/bin/env python
"""
    ..__main__.py
    ~~~~~~~~~~~~~~~~

    Picasso command line interface

    :author: Joerg Schnitzbauer, 2015
    :copyright: Copyright (c) 2015 Jungmann Lab, Max Planck Institute of Biochemistry
"""
import os.path


def _average(args):
    from glob import glob
    from .io import load_locs
    from .postprocess import average
    kwargs = {'iterations': args.iterations,
              'oversampling': args.oversampling}
    paths = glob(args.file)
    if paths:
        for path in paths:
            print('Averaging {}'.format(path))
            locs, info = load_locs(path)
            kwargs['path_basename'] = os.path.splitext(path)[0] + '_avg'
            average(locs, info, **kwargs)


def _hdf2visp(path, pixel_size):
    from glob import glob
    paths = glob(path)
    if paths:
        from .io import load_locs
        import os.path
        from numpy import savetxt
        for path in paths:
            print('Converting {}'.format(path))
            locs, info = load_locs(path)
            locs = locs[['x', 'y', 'z', 'photons', 'frame']].copy()
            locs.x *= pixel_size
            locs.y *= pixel_size
            outname = os.path.splitext(path)[0] + '.3d'
            savetxt(outname, locs, fmt=['%.1f', '%.1f', '%.1f', '%.1f', '%d'], newline='\r\n')


def _link(files, d_max, tolerance):
    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
        for path in paths:
            locs, info = io.load_locs(path)
            linked_locs = postprocess.link(locs, info, d_max, tolerance)
            base, ext = os.path.splitext(path)
            link_info = {'Maximum Distance': d_max,
                         'Maximum Transient Dark Time': tolerance,
                         'Generated by': 'Picasso Link'}
            info.append(link_info)
            io.save_locs(base + '_link.hdf5', linked_locs, info)


def _undrift(files, segmentation, display, fromfile):
    import glob
    from . import io, postprocess
    from numpy import genfromtxt, savetxt
    paths = glob.glob(files)
    undrift_info = {'Generated by': 'Picasso Undrift'}
    if fromfile is not None:
        undrift_info['From File'] = fromfile
        drift = genfromtxt(fromfile)
    else:
        undrift_info['Segmentation'] = segmentation
    for path in paths:
        locs, info = io.load_locs(path)
        info.append(undrift_info)
        if fromfile is not None:
            locs.x -= drift[:, 0][locs.frame]
            locs.y -= drift[:, 1][locs.frame]
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
            print('Undrifting file {}'.format(path))
            drift, locs = postprocess.undrift(locs, info, segmentation, display=True)
        base, ext = os.path.splitext(path)
        io.save_locs(base + '_undrift.hdf5', locs, info)
        savetxt(base + '_drift.txt', drift, header='dx\tdy', newline='\r\n')


def _density(files, radius):
    import glob
    paths = glob.glob(files)
    if paths:
        from . import io, postprocess
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
        from . import io, postprocess
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
        from . import io, postprocess
        for path in paths:
            locs, info = io.load_locs(path)
            locs = postprocess.compute_dark_times(locs)
            base, ext = os.path.splitext(path)
            dbscan_info = {'Generated by': 'Picasso Dark'}
            info.append(dbscan_info)
            io.save_locs(base + '_dark.hdf5', locs, info)


def _align(files, display):
    from glob import glob
    from itertools import chain
    from .io import load_locs, save_locs
    from .postprocess import align
    from os.path import splitext
    files = list(chain(*[glob(_) for _ in files]))
    print('Aligning files:')
    for f in files:
        print('  ' + f)
    locs_infos = [load_locs(_) for _ in files]
    locs = [_[0] for _ in locs_infos]
    infos = [_[1] for _ in locs_infos]
    aligned_locs = align(locs, infos, display=display)
    align_info = {'Generated by': 'Picasso Align',
                  'Files': files}
    for file, locs_, info in zip(files, aligned_locs, infos):
        info.append(align_info)
        base, ext = splitext(file)
        save_locs(base + '_align.hdf5', locs_, info)


def _join(files):
    from .io import load_locs, save_locs
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


def _groupprops(files):
    import glob
    paths = glob.glob(files)
    if paths:
        from .io import load_locs, save_datasets
        from .postprocess import groupprops
        from os.path import splitext
        for path in paths:
            locs, info = load_locs(path)
            groups = groupprops(locs)
            base, ext = splitext(path)
            save_datasets(base + '_groupprops.hdf5', info, locs=locs, groups=groups)


def _pair_correlation(files, bin_size, r_max):
    from glob import glob
    paths = glob(files)
    if paths:
        from .io import load_locs
        from .postprocess import pair_correlation
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


def _localize(files):
    from glob import glob
    from .io import load_movie, save_locs
    from .localize import identify_async, identifications_from_futures, fit_async, locs_from_fits
    from os.path import splitext
    from time import sleep
    paths = glob(files)
    if paths:
        def prompt_info():
            info = {}
            info['Byte Order'] = input('Byte Order (< or >): ')
            info['Data Type'] = input('Data Type (e.g. "uint16"): ')
            info['Frames'] = int(input('Frames: '))
            info['Height'] = int(input('Height: '))
            info['Width'] = int(input('Width: '))
            save = input('Save info to yaml file (y/n): ') == 'y'
            return info, save
        box = int(input('Box side length: '))
        min_net_gradient = float(input('Min. net gradient: '))
        camera_info = {}
        camera_info['baseline'] = float(input('Baseline: '))
        camera_info['sensitivity'] = float(input('Sensitivity: '))
        camera_info['gain'] = int(input('EM Gain: '))
        camera_info['qe'] = float(input('Quantum efficiency: '))
        convergence = float(input('Convergence criterion: '))
        max_iterations = int(input('Max. iterations: '))
    for path in paths:
        print('Processing {}'.format(path))
        movie, info = load_movie(path, prompt_info=prompt_info)
        current, futures = identify_async(movie, min_net_gradient, box)
        n_frames = len(movie)
        while current[0] < n_frames:
            print('Identifying in frame {:,} of {:,}'.format(current[0]+1, n_frames), end='\r')
            sleep(0.2)
        print('Identifying in frame {:,} of {:,}'.format(n_frames, n_frames))
        ids = identifications_from_futures(futures)
        current, thetas, CRLBs, likelihoods, iterations = fit_async(movie,
                                                                    camera_info,
                                                                    ids,
                                                                    box,
                                                                    convergence,
                                                                    max_iterations)
        n_spots = len(ids)
        while current[0] < n_spots:
            print('Fitting spot {:,} of {:,}'.format(current[0]+1, n_spots), end='\r')
            sleep(0.2)
        print('Fitting spot {:,} of {:,}'.format(n_spots, n_spots))
        locs = locs_from_fits(ids, thetas, CRLBs, likelihoods, iterations, box)
        localize_info = {'Generated by': 'Picasso Localize',
                         'ROI': None,
                         'Box Size': box,
                         'Min. Net Gradient': min_net_gradient,
                         'Convergence Criterion': convergence,
                         'Max. Iterations': max_iterations}
        info.append(localize_info)
        base, ext = splitext(path)
        out_path = base + '_locs.hdf5'
        save_locs(out_path, locs, info)


def _render(args):
    from .lib import locs_glob_map
    from .render import render
    from os.path import splitext
    from matplotlib.pyplot import imsave
    from os import startfile
    from .io import load_user_settings, save_user_settings

    def render_many(locs, info, path, oversampling, blur_method, min_blur_width, vmin, vmax, cmap, silent):
        if blur_method == 'none':
            blur_method = None
        N, image = render(locs, info, oversampling, blur_method=blur_method, min_blur_width=min_blur_width)
        base, ext = splitext(path)
        out_path = base + '.png'
        im_max = image.max() / 100
        imsave(out_path, image, vmin=vmin * im_max, vmax=vmax * im_max, cmap=cmap)
        if not silent:
            startfile(out_path)

    settings = load_user_settings()
    cmap = args.cmap
    if cmap is None:
        try:
            cmap = settings['Render']['Colormap']
        except KeyError:
            cmap = 'viridis'
    settings['Render']['Colormap'] = cmap
    save_user_settings(settings)

    locs_glob_map(render_many, args.files, args=(args.oversampling, args.blur_method, args.min_blur_width, args.vmin, args.vmax,
                                                 cmap, args.silent))


def main():
    import argparse

    # Main parser
    parser = argparse.ArgumentParser('picasso')
    subparsers = parser.add_subparsers(dest='command')

    for command in ['toraw', 'localize', 'filter', 'render']:
        subparsers.add_parser(command)

    # link parser
    link_parser = subparsers.add_parser('link', help='link localizations in consecutive frames')
    link_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')
    link_parser.add_argument('-d', '--distance', type=float, default=1.0,
                             help='maximum distance between localizations to consider them the same binding event (default=1.0)')
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

    # align
    align_parser = subparsers.add_parser('align', help='align one localization file to another')
    align_parser.add_argument('-d', '--display', help='display correlation', action='store_true')
    # align_parser.add_argument('-a', '--affine', help='include affine transformations (may take long time)', action='store_true')
    align_parser.add_argument('file', help='one or multiple hdf5 localization files', nargs='+')

    # join
    join_parser = subparsers.add_parser('join', help='join hdf5 localization lists')
    join_parser.add_argument('file', nargs='+', help='the hdf5 localization files to be joined')

    # group properties
    groupprops_parser = subparsers.add_parser('groupprops', help='calculate and various properties of localization groups')
    groupprops_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    # Pair correlation
    pc_parser = subparsers.add_parser('pc', help='calculate the pair-correlation of localizations')
    pc_parser.add_argument('-b', '--binsize', type=float, default=0.1, help='the bin size')
    pc_parser.add_argument('-r', '--rmax', type=float, default=10, help='The maximum distance to calculate the pair-correlation')
    pc_parser.add_argument('files', help='one or multiple hdf5 localization files specified by a unix style path pattern')

    # localize
    localize_parser = subparsers.add_parser('localize', help='identify and fit single molecule spots')
    localize_parser.add_argument('files', nargs='?', help='one or multiple movie files specified by a unix style path pattern')

    # render
    render_parser = subparsers.add_parser('render', help='render localization based images')
    render_parser.add_argument('files', nargs='?', help='one or multiple localization files specified by a unix style path pattern')
    render_parser.add_argument('-o', '--oversampling', type=float, default=1.0, help='the number of super-resolution pixels per camera pixels')
    render_parser.add_argument('-b', '--blur-method', choices=['none', 'convolve', 'gaussian'], default='convolve')
    render_parser.add_argument('-w', '--min-blur-width', type=float, default=0.0, help='minimum blur width if blur is applied')
    render_parser.add_argument('--vmin', type=float, default=0.0, help='minimum colormap level in range 0-100')
    render_parser.add_argument('--vmax', type=float, default=20.0, help='maximum colormap level in range 0-100')
    render_parser.add_argument('-c', '--cmap', choices=['viridis', 'inferno', 'plasma', 'magma', 'hot', 'gray'], help='the colormap to be applied')
    render_parser.add_argument('-s', '--silent', action='store_true', help='do not open the image file')

    # design
    subparsers.add_parser('design', help='design RRO DNA origami structures')
    # simulate
    subparsers.add_parser('simulate', help='simulate single molecule fluorescence data')

    # average
    average_parser = subparsers.add_parser('average', help='particle averaging')
    average_parser.add_argument('-o', '--oversampling', type=float, default=10,
                                help='oversampling of the super-resolution images for alignment evaluation')
    average_parser.add_argument('-i', '--iterations', type=int, default=20)
    average_parser.add_argument('files', nargs='?', help='a localization file with grouped localizations')

    hdf2visp_parser = subparsers.add_parser('hdf2visp')
    hdf2visp_parser.add_argument('files')
    hdf2visp_parser.add_argument('pixelsize', type=float)

    # Parse
    args = parser.parse_args()
    if args.command:
        if args.command == 'toraw':
            from .gui import toraw
            toraw.main()
        elif args.command == 'localize':
            if args.files:
                _localize(args.files)
            else:
                from .gui import localize
                localize.main()
        elif args.command == 'filter':
            from .gui import filter
            filter.main()
        elif args.command == 'render':
            if args.files:
                _render(args)
            else:
                from .gui import render
                render.main()
        elif args.command == 'average':
            if args.files:
                _average(args)
            else:
                from .gui import average
                average.main()
        elif args.command == 'link':
            _link(args.files, args.distance, args.tolerance)
        elif args.command == 'undrift':
            _undrift(args.files, args.segmentation, args.nodisplay, args.fromfile)
        elif args.command == 'density':
            _density(args.files, args.radius)
        elif args.command == 'dbscan':
            _dbscan(args.files, args.radius, args.density)
        elif args.command == 'dark':
            _dark(args.files)
        elif args.command == 'align':
            _align(args.file, args.display)
        elif args.command == 'join':
            _join(args.file)
        elif args.command == 'groupprops':
            _groupprops(args.files)
        elif args.command == 'pc':
            _pair_correlation(args.files, args.binsize, args.rmax)
        elif args.command == 'simulate':
            from .gui import simulate
            simulate.main()
        elif args.command == 'design':
            from .gui import design
            design.main()
        elif args.command == 'hdf2visp':
            _hdf2visp(args.files, args.pixelsize)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
