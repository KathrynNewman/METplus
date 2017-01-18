#!/usr/bin/python
from __future__ import print_function

import constants_pdef as P
import re
import os
import sys
import met_util as util
import subprocess


def analysis_by_lead_time():
    ''' Perform a series analysis of extra tropical cyclone
        paired data based on lead time (forecast hour) 
        This requires invoking the MET run_series_analysis binary,
        followed by generating graphics that are recognized by 
        the MET viewer using the plot_data_plane and convert.  
        A pre-requisite is the presence of the filter file and storm files
        (currently 30 x 30 degree tiles) for the specified init and lead times.
   

       Invoke the series_analysis script based on lead time (forecast hour) 
       Create the command:
         series_analysis -fcst <FILTERED_OUT_DIR>/FCST_FILES_F<CUR_FHR>
                         -obs <FILTERED_OUT_DIR>/ANLY_FILES_F<CUR_FHR>
                         -out <OUT_DIR>/series_F<CURR_FHR_<NAME>_<LEVEL>.nc 
                         -config SeriesAnalysisConfig_by_lead
      Args:
        None


      Returns:
        None:       Creates graphics plots for files corresponding to each
                    forecast lead time.


    '''
    # Create a param object
    p = P.Params()
    p.init()

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    # Retrieve any necessary values from the parm file(s)
    fhr_beg = p.opt["FHR_BEG"]
    fhr_end = p.opt["FHR_END"]
    fhr_inc = p.opt["FHR_INC"]
    fcst_tile_regex = p.opt["FCST_TILE_REGEX"]
    anly_tile_regex = p.opt["ANLY_TILE_REGEX"]
    var_list = p.opt["VAR_LIST"]
    stat_list = p.opt["STAT_LIST"]
    series_analysis_exe = p.opt["SERIES_ANALYSIS"]
    plot_data_plane_exe = p.opt["PLOT_DATA_PLANE"]
    rm_exe = p.opt["RM_EXE"]
    convert_exe = p.opt["CONVERT_EXE"]
    series_anly_configuration_file = p.opt["SERIES_ANALYSIS_BY_LEAD_CONFIG_PATH"]
    extract_tiles_dir = p.opt["EXTRACT_OUT_DIR"]
    series_lead_filtered_out_dir = p.opt["SERIES_LEAD_FILTERED_OUT_DIR"]
    series_lead_out_dir = p.opt["SERIES_LEAD_OUT_DIR"]
    background_map = p.opt["BACKGROUND_MAP"]
    regrid_with_MET_tool = p.opt["REGRID_USING_MET_TOOL"]
    series_filter_opts = p.opt["SERIES_ANALYSIS_FILTER_OPTS"]
    series_filter_opts.strip()

    # Set up the environment variable to be used in the Series Analysis
    #   Config file (SERIES_ANALYSIS_BY_LEAD_CONFIG_PATH)
    # Used to set cnt  value in output_stats in "SERIES_ANALYSIS_BY_LEAD_CONFIG_PATH"
    # Need to do some pre-processing so that Python will use " and not '
    #  because currently MET doesn't support single-quotes
    tmp_stat_string = str(stat_list)
    tmp_stat_string = tmp_stat_string.replace("\'", "\"")
    os.environ['STAT_LIST'] = tmp_stat_string

    if regrid_with_MET_tool:
        # Regridding via MET Tool regrid_data_plane.
        fcst_tile_regex = p.opt["FCST_NC_TILE_REGEX"]
        anly_tile_regex = p.opt["ANLY_NC_TILE_REGEX"]
    else:
        # Regridding via wgrib2 tool.
        fcst_tile_regex = p.opt["FCST_TILE_REGEX"]
        anly_tile_regex = p.opt["ANLY_TILE_REGEX"]

    # Check for the existence of the storm track tiles and raise
    # an error if these are missing.
    # Get a list of the grb2 forecast tiles in 
    # <project dir>/series_analysis/*/*/FCST_TILE_F<cur_fhr>.grb2
    logger.info("Begin series analysis by lead...")
    # Initialize the tile_dir to the extract tiles output directory.
    # And retrieve a list of init times based on the data available in
    # the extract tiles directory.
    tile_dir = extract_tiles_dir
    init_times = util.get_updated_init_times(tile_dir, p, logger)
    
    try:
        util.check_for_tiles(tile_dir, fcst_tile_regex, anly_tile_regex, logger)
    except OSError as e:
        msg = ("ERROR|[ " + cur_filename + ":" +
               cur_function + "]| Missing 30x30 tile files." +
               "  Extract tiles needs to be run")
        logger.error(msg)

    # Apply optional filtering via tc_stat, as indicated in the
    # constants_pdef.py parameter/config file.
    if series_filter_opts:
        util.mkdir_p(series_lead_filtered_out_dir)
        util.apply_series_filters(tile_dir, init_times, series_lead_filtered_out_dir, p, logger)

        # Remove any empty files and directories to avoid
        # errors or performance degradation when performing
        # series analysis.
        util.prune_empty(series_lead_filtered_out_dir, p, logger)

        # Get the list of all the files that were created as a result
        # of applying the filter options.  Save this information, it
        # will be useful for troubleshooting and validating the correctness
        # of filtering.

        # First, make sure that the series_lead_filtered_out directory isn't
        # empty.  If so, then no files fall within the filter criteria.
        if os.listdir(series_lead_filtered_out_dir):
            # Filtering produces results, assign the tile_dir to
            # the filter output directory, series_lead_filtered_out_dir.
            filtered_files_list = util.get_files(tile_dir, ".*.", logger)
            tile_dir = series_lead_filtered_out_dir

            # Create the tmp_fcst and tmp_anly ASCII files containing the
            # list of files that meet the filter criteria.
            util.create_filter_tmp_files(filtered_files_list, series_lead_filtered_out_dir, p, logger)
            tile_dir = series_lead_filtered_out_dir
        else:
            # No data meet filter criteria, use data from extract tiles directory.
            msg = ("After applying filter options, no data meet filter criteria." +
                   "Continue using all available data in extract tiles directory.")
            logger.debug(msg)
            tile_dir = extract_tiles_dir

    else:
        # No additional filtering was requested.  The extract tiles directory is the
        # source of input tile data.
        tile_dir = extract_tiles_dir

    # Create the values for the -fcst, -obs, and other required
    # options for running the MET series_analysis binary.

    for fhr in range(fhr_beg, fhr_end + 1, fhr_inc):
        cur_fhr = str(fhr).zfill(3)
        msg = ('INFO|[' + cur_filename + ':' + cur_function +
               ']| Evaluating forecast hour ' + cur_fhr)
        logger.debug(msg)

        # Create the output directory where the netCDF series files
        # will be saved.
        util.mkdir_p(series_lead_out_dir)
        out_dir_parts = [series_lead_out_dir, '/', 'series_F', cur_fhr]
        out_dir = ''.join(out_dir_parts)
        util.mkdir_p(out_dir)

        # Gather all the forecast gridded tile files
        # so they can be saved in ASCII files.
        fcst_tiles_list = get_anly_fcst_files(tile_dir, "FCST", fcst_tile_regex,
                                              cur_fhr, logger)
        fcst_tiles = retrieve_fhr_tiles(fcst_tiles_list, 'FCST', out_dir,
                                        cur_fhr, fcst_tile_regex, logger)

        # Location of FCST_FILES_Fhhh 
        ascii_fcst_file_parts = [out_dir, '/FCST_FILES_F', cur_fhr]
        ascii_fcst_file = ''.join(ascii_fcst_file_parts)

        # Now create the ASCII files needed for the -fcst and -obs
        try:
            if len(fcst_tiles) == 0:
                msg = ("INFO|[" + cur_filename + ":" +
                       cur_function + "No fcst_tiles for fhr: " + cur_fhr +
                       " Don't create FCST_F<fhr> ASCII file")
                logger.debug(msg)
                continue
            else:
                with open(ascii_fcst_file, 'a') as f:
                    f.write(fcst_tiles)

        except IOError as e:
            msg = ("ERROR: Could not create requested" +
                   " ASCII file: " + ascii_fcst_file)
            logger.error(msg)

        # Gather all the anly gridded tile files
        # so they can be saved in ASCII files.
        anly_tiles_list = get_anly_fcst_files(tile_dir, "ANLY", anly_tile_regex,
                                              cur_fhr, logger)
        anly_tiles = retrieve_fhr_tiles(anly_tiles_list, 'ANLY', out_dir,
                                        cur_fhr, anly_tile_regex, logger)

        # Location of ANLY_FILES_Fhhh files 
        # filtering.
        ascii_anly_file_parts = [out_dir, '/ANLY_FILES_F', cur_fhr]
        ascii_anly_file = ''.join(ascii_anly_file_parts)

        try:
            # Only write to the ascii_anly_file if 
            # the anly_tiles string isn't empty.
            if len(anly_tiles) == 0:
                msg = ("INFO|[" + cur_filename + ":" +
                       cur_function + "No anly_tiles for fhr: " + cur_fhr +
                       " Don't create ANLY_F<fhr> ASCII file")
                logger.debug(msg)
                continue
            else:
                with open(ascii_anly_file, 'a') as f:
                    f.write(anly_tiles)

        except IOError as e:
            logger.error("ERROR: Could not create requested " +
                         "ASCII file: " + ascii_anly_file)

        # Remove any empty directories that result from 
        # when no files are written.
        util.prune_empty(out_dir, p, logger)

        # -fcst and -obs params
        fcst_param_parts = ['-fcst ', ascii_fcst_file]
        fcst_param = ''.join(fcst_param_parts)
        obs_param_parts = ['-obs ', ascii_anly_file]
        obs_param = ''.join(obs_param_parts)
        logger.debug('fcst param: ' + fcst_param)
        logger.debug('obs param: ' + obs_param)

        # Create the -out param and invoke the MET series 
        # analysis binary
        for cur_var in var_list:
            # Get the name and level to create the -out param
            # and set the NAME and LEVEL environment variables that
            # are needed by the MET series analysis binary.
            match = re.match(r'(.*)/(.*)', cur_var)
            name = match.group(1)
            level = match.group(2)
            os.environ['NAME'] = name
            os.environ['LEVEL'] = level

            # Set NAME to name_level if regridding with regrid data plane
            if regrid_with_MET_tool:
                os.environ['NAME'] = name + '_' + level
            out_param_parts = ['-out ', out_dir, '/series_F', cur_fhr,
                               '_', name, '_', level, '.nc']
            out_param = ''.join(out_param_parts)

            # Create the full series analysis command.
            config_param_parts = ['-config ',
                                  series_anly_configuration_file]
            config_param = ''.join(config_param_parts)
            series_analysis_cmd_parts = [series_analysis_exe, ' ',
                                         ' -v 4 ',
                                         fcst_param, ' ', obs_param,
                                         ' ', config_param, ' ',
                                         out_param]
            series_analysis_cmd = ''.join(series_analysis_cmd_parts)
            msg = ("INFO:[ " + cur_filename + ":" +
                   cur_function + "]|series analysis command: " +
                   series_analysis_cmd)
            logger.debug(msg)
            series_out = subprocess.check_output(series_analysis_cmd,
                                                 stderr=subprocess.STDOUT,
                                                 shell=True)

    # Make sure there aren't any emtpy
    # files or directories that still persist.
    util.prune_empty(series_lead_out_dir, p, logger)

    # Now create animation plots
    animate_dir = os.path.join(series_lead_out_dir, 'series_animate')
    msg = ('INFO|[' + cur_filename + ':' + cur_function +
           ']| Creating Animation Plots, create directory:' +
           animate_dir)
    logger.debug(msg)
    util.mkdir_p(animate_dir)

    # Generate a plot for each variable, statistic, and lead time.
    # First, retrieve all the netCDF files that were generated 
    # above by the run series analysis.
    logger.info('GENERATING PLOTS...')

    # Retrieve a list of all the netCDF files generated by 
    # MET Tool series analysis.
    nc_list = retrieve_nc_files(series_lead_out_dir, logger)

    # Check that we have netCDF files, if not, something went
    # wrong.
    if len(nc_list) == 0:
        logger.error("ERROR|" + cur_filename + ":" + cur_function +
                     "]|  could not find any netCDF files to convert to PS and PNG. "+
                     "Exiting...")
        sys.exit(1)
    else:
        msg = ("INFO|[" + cur_filename + ":" + cur_function +
               " Number of nc files found to convert to PS and PNG  : " +
               str(len(nc_list)))
        logger.debug(msg)

    for cur_var in var_list:
        # Get the name and level to set the NAME and LEVEL
        # environment variables that
        # are needed by the MET series analysis binary.
        match = re.match(r'(.*)/(.*)', cur_var)
        name = match.group(1)
        level = match.group(2)

        os.environ['NAME'] = name
        os.environ['LEVEL'] = level

        if regrid_with_MET_tool:
            os.environ['NAME'] = name + '_' + level

        # Retrieve only those netCDF files that correspond to
        # the current variable.
        nc_var_list = get_var_ncfiles(name, nc_list, logger)
        if len(nc_var_list) == 0:
            logger.debug("WARNING nc_var_list is empty, check for next variable...")
            continue

        # Iterate over the statistics, setting the CUR_STAT
        # environment variable...
        for cur_stat in stat_list:
            # Set environment variable required by MET
            # application Plot_Data_Plane.
            os.environ['CUR_STAT'] = cur_stat
            vmin, vmax = get_netcdf_min_max(nc_var_list, cur_stat, p, logger)
            msg = ("|INFO|[ " + cur_filename + ":" + cur_function +
                   "]| Plotting range for " + cur_var + " " +
                   cur_stat + ":  " + str(vmin) + " to " + str(vmax))
            logger.debug(msg)

            # Plot the output for each time
            # DEBUG
            logger.info("Create PS and PNG")
            for cur_nc in nc_var_list:
                # The postscript files are derived from
                # each netCDF file. The postscript filename is
                # created by replacing the '.nc' extension
                # with '_<cur_stat>.ps'. The png file is created
                # by replacing the '.ps'
                # extension of the postscript file with '.png'.
                repl_string = ['_', cur_stat, '.ps']
                repl = ''.join(repl_string)
                ps_file = re.sub('(\.nc)$', repl, cur_nc)

                # Now create the PNG filename from the
                # Postscript filename.
                png_file = re.sub('(\.ps)$', '.png', ps_file)

                # Extract the forecast hour from the netCDF
                # filename.
                match_fhr = re.match(
                    r'.*/series_F\d{3}/series_F(\d{3}).*\.nc', cur_nc)
                if match_fhr:
                    fhr = match_fhr.group(1)
                else:
                    msg = ("WARNING: netCDF file format is " +
                           "unexpected. Try next file in list...")
                    logger.debug(msg)
                    continue

                # Get the max series_cnt_TOTAL value (i.e. nseries)
                nseries = get_nseries(cur_nc, p, logger)

                # Create the plot data plane command.
                if background_map:
                    # Flag set to True, print background map.
                    map_data = ''
                else:
                    map_data = "map_data={source=[];}  "

                plot_data_plane_parts = [plot_data_plane_exe, ' ',
                                         cur_nc, ' ', ps_file, ' ',
                                         "'", 'name = ', '"',
                                         'series_cnt_', cur_stat, '";',
                                         'level=', '"(\*,\*)"; ',
                                         ' ', map_data,
                                         "'", ' -title ', '"GFS F',
                                         str(fhr),
                                         ' Forecasts (N = ', str(nseries),
                                         '), ', cur_stat, ' for ', cur_var,
                                         '"', ' -plot_range ', str(vmin),
                                         ' ', str(vmax)]
 
                plot_data_plane_cmd = ''.join(plot_data_plane_parts)
                msg = ("INFO|[" + cur_filename + ":" +
                       cur_function + "]| plot_data_plane cmd: " +
                       plot_data_plane_cmd)
                logger.debug(msg)

                # Create the command based on whether or not
                # the background map was requested in the
                # constants_pdef.py param/config file.
                if background_map:
                    # Flag set to True, print background map.
                    map_data = ''
                else:
                    map_data = "map_data={source=[];}  "

                plot_data_plane_parts = [plot_data_plane_exe, ' ',
                                         cur_nc, ' ', ps_file, ' ',
                                         "'", 'name = ', '"',
                                         'series_cnt_', cur_stat, '";',
                                         'level=', '"(\*,\*)"; ',
                                         ' ', map_data,
                                         "'", ' -title ', '"GFS F',
                                         str(fhr),
                                         ' Forecasts (N = ', str(nseries),
                                         '), ', cur_stat, ' for ', cur_var,
                                         '"', ' -plot_range ', str(vmin),
                                         ' ', str(vmax)]

                plot_data_plane_cmd = ''.join(plot_data_plane_parts)
                msg = ("INFO|[" + cur_filename + ":" +
                       cur_function + "]| plot_data_plane cmd: " +
                       plot_data_plane_cmd)
                logger.debug(msg)
                plot_out = subprocess.check_output(plot_data_plane_cmd,
                                                   stderr=subprocess.STDOUT,
                                                   shell=True)

                # Create the convert command.
                convert_parts = [convert_exe, ' -rotate 90 ',
                                 ' -background white -flatten ',
                                 ps_file, ' ', png_file]
                convert_cmd = ''.join(convert_parts)
                convert_out = subprocess.check_output(convert_cmd,
                                                      stderr=
                                                      subprocess.STDOUT,
                                                      shell=True)

            # Create animated gif
            logger.info("Creating animated gifs")
            gif_parts = [convert_exe,
                         ' -dispose Background -delay 100 ',
                         series_lead_out_dir, '/series_F*',
                         '/series_F*', '_', name, '_',
                         level, '_', cur_stat, '.png', '  ',
                         animate_dir, '/series_animate_', name, '_',
                         level, '_', cur_stat, '.gif']
            animate_cmd = ''.join(gif_parts)
            msg = ("INFO|[" + cur_filename + ":" + cur_function +
                   "]| animate command: " + animate_cmd)
            logger.debug(msg)
            animate_out = subprocess.check_output(animate_cmd,
                                                  stderr=subprocess.STDOUT,
                                                  shell=True)

    logger.info("Finished with series analysis by lead")


def get_nseries(nc_var_file, p, logger):
    '''Determine the number of series for this lead time and
       its associated variable via calculating the max series_cnt_TOTAL 
       value.

       Args:
             nc_var_file:  The netCDF file for a particular variable.
             p:             The ConfigMaster object.
             logger:        The logger to which all log messages are
                            sent.


       Returns:
             max (float):   The maximum value of series_cnt_TOTAL of all
                            the netCDF files for the variable cur_var.

             None:          If no max value is found.


    '''

    # Retrieve any necessary things from the config/param file.
    rm_exe = p.opt["RM_EXE"]
    ncap2_exe = p.opt["NCAP2_EXE"]
    ncdump_exe = p.opt["NCDUMP_EXE"]

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    # Determine the series_F<fhr> subdirectory where this netCDF file
    # resides.
    match = re.match(r'(.*/series_F[0-9]{3})/series_F[0-9]{3}.*nc',
                     nc_var_file)
    if match:
        base_nc_dir = match.group(1)
    else:
        msg = ("ERROR\[" + cur_filename + ":" +
               cur_function + "]| " +
               "Cannot determine base directory path for " +
               "netCDF files... exiting")
        logger.error(msg)
        sys.exit(1)

    # Use NCO utility ncap2 to find the max for 
    # the variable and series_cnt_TOTAL pair.
    nseries_nc_path = os.path.join(base_nc_dir, 'nseries.nc')
    nco_nseries_cmd_parts = [ncap2_exe, ' -v -s ', '"',
                             'max=max(series_cnt_TOTAL)', '" ',
                             nc_var_file, ' ', nseries_nc_path]
    nco_nseries_cmd = ''.join(nco_nseries_cmd_parts)
    nco_out = subprocess.check_output(nco_nseries_cmd,
                                      stderr=subprocess.STDOUT,
                                      shell=True)

    # Create an ASCII file with the max value, which can be parsed.
    nseries_txt_path = os.path.join(base_nc_dir, 'nseries.txt')
    ncdump_max_cmd_parts = [ncdump_exe, ' ', base_nc_dir,
                            '/nseries.nc > ', nseries_txt_path]
    ncdump_max_cmd = ''.join(ncdump_max_cmd_parts)
    ncdump_out = subprocess.check_output(ncdump_max_cmd,
                                         stderr=subprocess.STDOUT,
                                         shell=True)
    # Look for the max value for this netCDF file.
    try:
        with open(nseries_txt_path, 'r') as fmax:
            for line in fmax:
                max_match = re.match(r'\s*max\s*=\s([-+]?\d*\.*\d*)', line)
                if max_match:
                    max = max_match.group(1)

                    # Clean up any intermediate .nc and .txt files
                    nseries_list = [rm_exe, ' ', base_nc_dir, '/nseries.*']
                    nseries_cmd = ''.join(nseries_list)
                    os.system(nseries_cmd)
                    return max

    except IOError as e:
        msg = ("ERROR|[" + cur_filename + ":" +
               cur_function + "]| cannot open the min text file")
        logger.error(msg)


def get_netcdf_min_max(nc_var_files, cur_stat, p, logger):
    '''Determine the min and max for all lead times for each 
       statistic and variable pairing.

       Args:
           nc_var_files:  A list of the netCDF files generated 
                          by the MET series analysis tool that 
                          correspond to the variable of interest.
           cur_stat:      The current statistic of interest: RMSE, 
                          MAE, ODEV, FDEV, ME, or TOTAL.
           p:             The ConfigMaster object, used to retrieve
                          values from the config/param file.
           logger:        The logger to which all log messages are 
                          directed.
          
       Returns:
           tuple (vmin, vmax)
               VMIN:  The minimum
               VMAX:  The maximum
       
    '''

    ncap2_exe = p.opt["NCAP2_EXE"]
    ncdump_exe = p.opt["NCDUMP_EXE"]
    rm_exe = p.opt["RM_EXE"]

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    # Initialize the threshold values for min and max.
    VMIN = 999999.
    VMAX = -999999.

    for cur_nc in nc_var_files:
        # Determine the series_F<fhr> subdirectory where this 
        # netCDF file resides.
        match = re.match(r'(.*/series_F[0-9]{3})/series_F[0-9]{3}.*nc', cur_nc)
        if match:
            base_nc_dir = match.group(1)
            logger.debug("base nc dir: " + base_nc_dir)
        else:
            msg = ("ERROR|[" + cur_filename + ":" + cur_function +
                   "]| Cannot determine base directory path " +
                   "for netCDF files. Exiting...")
            logger.error(msg)
            sys.exit(1)

        # Use NCO utility ncap2 to find the min and max for 
        # the variable and stat pair.

        # MIN VALUE from netCDF
        min_nc_path = os.path.join(base_nc_dir, 'min.nc')
        min_txt_path = os.path.join(base_nc_dir, 'min.txt')

        # First, remove any pre-existing min.nc and
        # min.txt files from a previous run.
        try:
            os.remove(min_nc_path)
            os.remove(min_txt_path)
        except OSError as e:
            # Exception can be raised if these
            # files don't exist.
            pass
            logger.debug("WARNING|[" + cur_filename + cur_function +
                         "]| " + str(e))

        nco_min_cmd_parts = [ncap2_exe, ' -v -s ', '"',
                             'min=min(series_cnt_', cur_stat, ')',
                             '" ', cur_nc, ' ', min_nc_path]
        nco_min_cmd = ''.join(nco_min_cmd_parts)
        logger.debug('nco_min_cmd: ' + nco_min_cmd)
        nco_min_out = subprocess.check_output(nco_min_cmd,
                                              stderr=subprocess.STDOUT,
                                              shell=True)

        # MAX VALUE from netCDF
        max_nc_path = os.path.join(base_nc_dir, 'max.nc')
        max_txt_path = os.path.join(base_nc_dir, 'max.txt')

        # First, remove pre-existing max.nc file from any previous run.
        try:
            os.remove(max_nc_path)
            os.remove(max_txt_path)
        except OSError as e:
            # If already removed or never created, this will 
            # raise an exception.
            pass
            logger.warn("WARN|[" + cur_filename + cur_function +
                         "]| " + str(e))

        nco_max_cmd_parts = [ncap2_exe, ' -v -s ', '"',
                             'max=max(series_cnt_', cur_stat, ')',
                             '" ', cur_nc, ' ', max_nc_path]
        nco_max_cmd = ''.join(nco_max_cmd_parts)
        logger.debug('!!!nco_max_cmd: ' + nco_max_cmd)
        nco_max_out = subprocess.check_output(nco_max_cmd,
                                              stderr=subprocess.STDOUT,
                                              shell=True)

        # Create ASCII files with the min and max values, using
        # NCO utility ncdump. 
        # These files can be parsed to find the VMIN and VMAX.
        ncdump_min_cmd_parts = [ncdump_exe, ' ', base_nc_dir, '/min.nc > ', min_txt_path]
        ncdump_min_cmd = ''.join(ncdump_min_cmd_parts)
        ncdump_min_out = subprocess.check_output(ncdump_min_cmd,
                                                 stderr=subprocess.STDOUT,
                                                 shell=True)
        ncdump_max_cmd_parts = [ncdump_exe, ' ', base_nc_dir,
                                '/max.nc > ', max_txt_path]
        ncdump_max_cmd = ''.join(ncdump_max_cmd_parts)
        ncdump_max_out = subprocess.check_output(ncdump_max_cmd,
                                                 stderr=subprocess.STDOUT, shell=True)

        # Look for the min and max values in each netCDF file.
        try:
            with open(min_txt_path, 'r') as fmin:
                for line in fmin:
                    min_match = re.match(r'\s*min\s*=\s([-+]?\d*\.*\d*)',
                                         line)
                    if min_match:
                        cur_min = float(min_match.group(1))
                        if cur_min < VMIN:
                            VMIN = cur_min
        except IOError as e:
            msg = ("ERROR|[" + cur_filename + ":" + cur_function +
                   "]| cannot open the min text file")
            logger.error(msg)
        try:
            with open(max_txt_path, 'r') as fmax:
                for line in fmax:
                    max_match = re.match(r'\s*max\s*=\s([-+]?\d*\.*\d*)',
                                         line)
                    if max_match:
                        cur_max = float(max_match.group(1))
                        if cur_max > VMAX:
                            VMAX = cur_max
        except IOError as e:
            msg = ("ERROR|[" + cur_filename + ":" + cur_function +
                   "]| cannot open the max text file")
            logger.error(msg)


    return VMIN, VMAX


def get_var_ncfiles(cur_var, nc_list, logger):
    ''' Retrieve only the netCDF files corresponding to this statistic
        and variable pairing.

        Args:
            cur_var:   The variable of interest.
            nc_list:  The list of all netCDF files that were generated 
                      by the MET utility run_series_analysis.
            logger:  The logger to which all logging messages are sent

        Returns:
            var_ncfiles: A list of netCDF files that
                              correspond to this variable.

    '''

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    # Create the regex to retrieve the variable name.
    # The variable is contained in the netCDF file name.
    var_ncfiles = []
    var_regex_parts = [".*series_F[0-9]{3}_", cur_var,
                       "_[0-9a-zA-Z]+.*nc"]
    var_regex = ''.join(var_regex_parts)
    for cur_nc in nc_list:
        # Determine the variable from the filename
        match = re.match(var_regex, cur_nc)
        if match:
            var_ncfiles.append(cur_nc)

    # Do some checking- the number var_ncfiles 
    # should be less than the total number of ncfiles.
    num_var = len(var_ncfiles)
    num_tot = len(nc_list)
    if num_var == num_tot:
        msg = ("ERROR|[" + cur_filename + ":" + cur_function +
               "]| the number of netCDF for variable" + cur_var +
               " is an inconsistent value, exiting...")
        logger.error(msg)
    return var_ncfiles


def retrieve_nc_files(base_dir, logger):
    '''Retrieve all the netCDF files that were created by the 
       MET series analysis binary.
       
       Args:
           base_dir: The base directory where all the 
                     series_F<fcst hour> sub-directories
                     are located.  The corresponding variable and 
                     statistic files for these forecast hours are 
                     found in these sub-directories.
                   
           logger:  The logger to which all log messages are directed.

       Returns:
           nc_list:  A list of the netCDF files (full path) created 
                     when the MET series analysis binary was invoked.
    '''

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    nc_list = []
    filename_regex = "series_F[0-9]{3}.*nc"

    # Get a list of all the series_F* directories
    # Use the met_utils function get_dirs to get only
    # the directories, as we are also generating
    # ASCII tmp_fcst and tmp_anly files in the
    # base_dir, which can cause problems if included in
    # the series_dir_list.
    series_dir_list = util.get_dirs(base_dir, p, logger)

    # Iterate through each of these series subdirectories
    # and create a list of all the netCDF files (full file path).
    for dir in series_dir_list:
        full_path = os.path.join(base_dir, dir)

        # Get a list of all the netCDF files for this subdirectory.
        nc_files_list = [f for f in os.listdir(full_path) if
                         os.path.isfile(os.path.join(full_path, f))]
        for cur_nc in nc_files_list:
            match = re.match(filename_regex, cur_nc)
            if match:
                nc_file = os.path.join(full_path, cur_nc)
                nc_list.append(nc_file)

    return nc_list


def retrieve_fhr_tiles(tile_list, file_type, cur_fhr, out_dir,
                       type_regex, logger):
    ''' Retrieves only the gridded tile files that
        correspond to the type.
        
        Args:
           tile_list:  List of tiles (full filepath).
           file_type : FCST or ANLY
           cur_fhr:    The current forecast hour
           out_dir:    The output directory 
           type_regex: The regex that corresponds to the tile 
                       filename for this type
           logger:     Logger to which all logging messages are passed.
        
        Returns:
           fhr_tiles (string):  A string of gridded tile names 
                                separated by newlines
    '''

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    type = file_type.upper()
    fhr_tiles = ''
    for cur_tile in tile_list:
        match = re.match(type_regex, cur_tile)
        if match:
            storm_subdir = match.group(0)
        else:
            msg = ("ERROR|[" + cur_filename + ":" +
                   cur_function +
                   "]| No matching storm id found, exiting...")
            logger.error(msg)
            return ''

        # Create the ASCII files for the forecast or analysis files
        if type == 'FCST':
            filename_base = 'FCST_FILES_F'
        else:
            filename_base = 'ANLY_FILES_F'

        tile_hr_parts = [filename_base, cur_fhr]
        tile_hr_dir = ''.join(tile_hr_parts)
        tile_full_filename = os.path.join(out_dir, tile_hr_dir)

        fhr_tiles += cur_tile
        fhr_tiles += '\n'

    return fhr_tiles


def find_matching_tile(fcst_file, anly_tiles, logger):
    ''' Find the corresponding ANLY 30x30 tile file to the 
        fcst tile file.
       
        Args:
          fcst_file_list (string):  The fcst file (full path) that 
                               is used to derive the corresponding
                               analysis file name.
          anly_tiles : The list of all available 30x30 analysis tiles.
          
          logger     : The logger to which all logging messages are
                       directed.

        Returns:
          anly_from_fcst (string): The name of the analysis tile file
                                   that corresponds to the same lead 
                                   time as the input fcst tile. 
    '''

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    # Derive the ANLY file name from the FCST file.
    anly_from_fcst = re.sub(r'FCST', 'ANLY', fcst_file)

    if anly_from_fcst in anly_tiles:
        return anly_from_fcst
    else:
        return None


def get_anly_fcst_files(filedir, type, filename_regex, cur_fhr, logger):
    ''' Get all the ANLY or FCST files by walking 
        through the directories starting at filedir.
    
        Args:
          filedir (String):  The topmost directory from which the
                             search begins.
          type:  FCST or ANLY
          filename_regex (string):  The regular expression that
                                    defines the naming format
                                    of the files of interest.

          cur_fhr: The current forecast hour for which we need to 
                   find the corresponding file

          logger:  The logger to which all log messages will be
                   directed.
       Returns:
          file_paths (string): a list of filenames (with full filepath)       

    '''

    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    file_paths = []

    # Walk the tree
    for root, directories, files in os.walk(filedir):
        for filename in files:
            # add it to the list only if it is a match
            # to the specified format
            # prog = re.compile(filename_regex)
            match = re.match(filename_regex, filename)
            if match:
                # Now match based on the current forecast hour
                if type == 'FCST':
                    match_fhr = re.match(r'.*FCST_TILE_F([0-9]{3}).*',
                                         match.group())
                elif type == 'ANLY':
                    match_fhr = re.match(r'.*ANLY_TILE_F([0-9]{3}).*',
                                         match.group())

                if match_fhr:
                    if match_fhr.group(1) == cur_fhr:
                        # Join the two strings to form the full
                        # filepath.
                        filepath = os.path.join(root, filename)
                        file_paths.append(filepath)
            else:
                continue
    return file_paths


def cleanup_lead_ascii(p, logger):
    ''' Remove any pre-existing FCST and ANLY ASCII files 
        created by previous runs of series_by_lead.
        

        Args:
           p       : The ConfigMaster, used to retrieve the  
                     parameter values
           logger  : The logger to which all log messages are directed.
     
        Returns:
           None:    Removes any existing FCST and ANLY ASCII files 
                    which contains all the forecast and analysis 
                    gridded tiles.
    '''

    # Useful for logging
    cur_filename = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name

    fhr_beg = p.opt["FHR_BEG"]
    fhr_end = p.opt["FHR_END"]
    fhr_inc = p.opt["FHR_INC"]
    fcst_ascii_regex = p.opt["FCST_ASCII_REGEX_LEAD"]
    anly_ascii_regex = p.opt["ANLY_ASCII_REGEX_LEAD"]
    rm_exe = p.opt["RM_EXE"]
    out_dir_base = p.opt["SERIES_LEAD_OUT_DIR"]

    for fhr in range(fhr_beg, fhr_end + 1, fhr_inc):
        cur_fhr = str(fhr).zfill(3)
        out_dir_parts = [out_dir_base, '/', 'series_F', cur_fhr]
        out_dir = ''.join(out_dir_parts)

        for root, directories, files in os.walk(out_dir):
            for cur_file in files:
                fcst_match = re.match(fcst_ascii_regex, cur_file)
                anly_match = re.match(anly_ascii_regex, cur_file)
                rm_file = os.path.join(out_dir, cur_file)
                if fcst_match:
                    os.remove(rm_file)
                if anly_match:
                    os.remove(rm_file)


if __name__ == "__main__":
    # Create ConfigMaster parm object
    p = P.Params()
    p.init(__doc__)
    logger = util.get_logger(p)
    analysis_by_lead_time()
