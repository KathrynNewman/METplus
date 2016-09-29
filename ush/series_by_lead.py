#!/usr/bin/python
from __future__ import print_function

import constants_pdef as P
import logging
import string
import re
import os
import sys
import met_util as util
import errno



def analysis_by_lead_time(p, logger):
    ''' Perform a series analysis of extra tropical cyclone
        paired data based on lead time (forecast hour) 
        This requires invoking the MET run_series_analysis binary,
        followed by generating graphics that are recognized by 
        the MET viewer using the plot_data_plane and convert.  
        A pre-requisite is the presence of the filter file and storm files
        (currently 30 x 30 degree tiles) for the specified init and lead times.
   

       Invoke the series_analysis script based on lead time (forecast hour) 
       Create the command:
         series_analysis -fcst <OUT_DIR>/FCST_FILES_F<CUR_FHR>
                         -obs <OUT_DIR>/ANLY_FILES_F<CUR_FHR>
                         -out <OUT_DIR>/series_F<CURR_FHR_<NAME>_<LEVEL>.nc 
                         -config SeriesAnalysisConfig_by_lead
      Args:
        p:          ConfigMaster parameter object 

        logger  :   The logging object to which logging will be saved.




      Returns:
        None:       Creates graphics plots for files corresponding to each
                    forecast lead time.


    '''
    # Create a param object
    p = P.Params()
    p.init(__doc__)
    
    cur_ = sys._getframe().f_code.co_filename
    cur_function = sys._getframe().f_code.co_name 
    
    # Retrieve any necessary values from the parm file(s)
    fhr_beg = p.opt["FHR_BEG"]
    fhr_end = p.opt["FHR_END"]
    fhr_inc = p.opt["FHR_INC"]
    fcst_tile_regex = p.opt["FCST_TILE_REGEX"]
    anly_tile_regex = p.opt["ANLY_TILE_REGEX"]
    fcst_ascii_regex = p.opt["FCST_ASCII_REGEX_LEAD"]
    anly_ascii_regex = p.opt["ANLY_ASCII_REGEX_LEAD"]
    proj_dir = p.opt["PROJ_DIR"]
    out_dir_base = p.opt["OUT_DIR"]
    var_list = p.opt["VAR_LIST"]
    stat_list = p.opt["STAT_LIST"]
    series_analysis_exe = p.opt["SERIES_ANALYSIS"]
    plot_data_plane_exe = p.opt["PLOT_DATA_PLANE"]
    convert_exe = p.opt["CONVERT_EXE"]
    rm_exe = p.opt["RM_EXE"]
    series_anly_configuration_file = p.opt["CONFIG_FILE_LEAD"]
    ncap2_exe = p.opt["NCAP2_EXE"]
    ncdump_exe = p.opt["NCDUMP_EXE"]
 
    # Check for the existence of the storm track tiles and raise an error if these are missing.
    # Get a list of the grb2 forecast tiles in <proj_dir>/series_analysis/*/*/FCST_TILE_F<cur_fhr>.grb2
    tile_dir_parts = [proj_dir,'/series_analysis/']
    tile_dir = ''.join(tile_dir_parts)
    try:
        util.check_for_tiles(tile_dir, fcst_tile_regex, anly_tile_regex, logger)
    except OSError as e:
        logger.error("Missing 30x30 tile files.  Extract tiles needs to be run")
        raise
        
    # Clean up any previous ASCII files that were generated by 
    # earlier runs of the series analysis.
    cleanup_lead_ascii(p, logger)    
  
    
    # Create the values for the -fcst, -obs, and other required
    # options for running the MET series_analysis binary.
    for fhr in range(fhr_beg, fhr_end+1, fhr_inc):
        cur_fhr = str(fhr).zfill(3)
        logger.info('Evaluating forecast hour ' + cur_fhr)

        # Create the output directory where the netCDF files
        # will be saved.
        out_dir_parts = [out_dir_base, '/', 'series_F', cur_fhr]
        out_dir = ''.join(out_dir_parts)
        util.mkdir_p(out_dir)
        
        # Gather all the forecast gridded tile files
        # so they can be saved in ASCII files.
        fcst_tiles_list = get_files(tile_dir,"FCST",fcst_tile_regex, cur_fhr, logger)
        fcst_tiles = retrieve_fhr_tiles(fcst_tiles_list,'FCST',out_dir, cur_fhr, fcst_tile_regex,logger)
        ascii_fcst_file_parts = [out_dir, '/FCST_FILE_F',cur_fhr]
        ascii_fcst_file = ''.join(ascii_fcst_file_parts)


        # Gather all the analysis gridded tile files
        # so they can be saved in ASCII files.
        anly_tiles_list = get_files(tile_dir,"ANLY", anly_tile_regex, cur_fhr, logger)
        anly_tiles = retrieve_fhr_tiles(anly_tiles_list,'ANLY',out_dir, cur_fhr, anly_tile_regex,logger)
        ascii_anly_file_parts = [out_dir, '/ANLY_FILE_F',cur_fhr]
        ascii_anly_file = ''.join(ascii_anly_file_parts)
            
        # Now create the ASCII files needed for the -fcst and -obs 
        try:
           with open(ascii_fcst_file, 'a') as f:
                f.write(fcst_tiles)
        except IOError as e:
            logger.error("ERROR: Could not create requested ASCII file: " + ascii_fcst_file)

        try:
            with open(ascii_anly_file, 'a') as f:
                f.write(anly_tiles)
        except IOError as e:
            logger.error("ERROR: Could not create requested ASCII file: " + ascii_anly_file)

        # -fcst and -obs params
        fcst_param_parts = ['-fcst ', ascii_fcst_file]
        fcst_param = ''.join(fcst_param_parts)
        obs_param_parts = [ '-obs ', ascii_anly_file]
        obs_param = ''.join(obs_param_parts)
        logger.info('fcst param: ' + fcst_param)
        logger.info('obs param: ' + obs_param)
      
        # Create the -out param and invoke the MET series analysis binary
        for cur_var in var_list:
            # Get the name and level to create the -out param
            # and set the NAME and LEVEL environment variables that
            # are needed by the MET series analysis binary.
            match = re.match(r'(.*)/(.*)',cur_var)
            name = match.group(1)
            level = match.group(2)
            os.environ['NAME'] = name
            os.environ['LEVEL'] = level
            out_param_parts = ['-out ', out_dir, '/series_F', cur_fhr, '_', name, '_', level, '.nc'] 
            out_param = ''.join(out_param_parts)
            logger.info("out param: " + out_param)

            # Create the full series analysis command.
            config_param_parts = ['-config ', series_anly_configuration_file]
            config_param = ''.join(config_param_parts)
            series_analysis_cmd_parts = [series_analysis_exe, ' ', fcst_param, ' ', obs_param, ' ', config_param, ' ', out_param]
            series_analysis_cmd = ''.join(series_analysis_cmd_parts)
            logger.info(" series analysis command: " + series_analysis_cmd)
            #os.system(series_analysis_cmd)

    # Now create animation plots
    animate_dir = os.path.join(out_dir, 'series_animate')
    util.mkdir_p(animate_dir)
   
    # Generate a plot for each variable, statistic, and lead time.
    # First, retrieve all the netCDF files that were generated above by the run series analysis.
    logger.info('GENERATING PLOTS...')
    nc_out_dir = out_dir_base
    nc_list = retrieve_nc_files(nc_out_dir,logger)
    if len(nc_list) == 0:
        logger.error("ERROR: cannot find netCDF files!")
        sys.exit()

    for cur_var in var_list: 
            # Get the name and level to set the NAME and LEVEL
            # environment variables that
            # are needed by the MET series analysis binary.
            match = re.match(r'(.*)/(.*)',cur_var)
            name = match.group(1)
            level = match.group(2)
            os.environ['NAME'] = name
            os.environ['LEVEL'] = level
           
            # Retrieve only those netCDF files that correspond to 
            # the current variable.
            nc_var_list = get_var_ncfiles(name, nc_list,logger)
            if len(nc_var_list) == 0:
                logger.error("ERROR nc_var_list is empty, exiting...")
                sys.exit()

            # Iterate over the statistics, setting the CUR_STAT
            # environment variable...
            for cur_stat in stat_list:
                # Set environment variable required by MET application Plot_Data_Plane.
                os.environ['CUR_STAT'] = cur_stat
                vmin, vmax = get_min_max(nc_var_list, cur_stat, p, logger)  
                logger.info("Plotting range for " + name + " " + cur_stat + ": "+ str(vmin) + " to " + str(vmax))
            
                # Plot the output for each time
                for cur_nc in nc_var_list:
                    # Create the postscript and PNG filenames. The postscript files are derived from 
                    # each netCDF file. The postscript filename is created by replacing the '.nc' extension
                    # with '_<cur_stat>.ps'. The png file is created by replacing the '.ps'
                    # extension of the postscript file with '.png'.
                    repl_string = ['_', cur_stat, '.ps']
                    repl = ''.join(repl_string)
                    print("cur nc to be modified: {}".format(cur_nc))
                    ps_file = re.sub('(\.nc)$', repl, cur_nc)                     
                    print("ps file: {} from cur nc: {} ".format(cur_nc, ps_file))
      
                    # Now create the PNG filename from the Postscript filename.
                    png_file = re.sub('(\.ps)$', '.png', ps_file) 
                    print("PNG file: {} from original {}: ".format(png_file, cur_nc))
              
                    # Extract the forecast hour from the netCDF filename.
                    match_fhr = re.match(r'.*/series_F\d{3}/series_F(\d{3}).*\.nc', cur_nc)
                    if match_fhr:
                        print("matching fhr found: {}".format(match_fhr.group(1)))
                        fhr = match_fhr.group(1)

                    # Get the max series_cnt_TOTAL value  
                    cleanup_min_max_tempfiles('max.nc',p, logger)
                    cleanup_min_max_tempfiles('min.nc',p, logger)
                    cleanup_min_max_tempfiles('max.out',p, logger)
                    cleanup_min_max_tempfiles('min.out',p, logger)
                    nseries_min, nseries_max = get_min_max(nc_var_list, 'TOTAL', p, logger)  
                    print("TOTAL nseries max: {}".format(nseries_max))
  
                    # Create the plot data plane command.
                    plot_data_plane_parts = [plot_data_plane_exe, ' ', cur_nc, ' ']
                    plot_data_plane_cmd = ''.join(plot_data_plane_parts)
                    print("plot data plane cmd: {} ".format(plot_data_plane_cmd))
                  
                    # Create the convert command.
                    #convert_parts = [convert_ext, ' -dispose Background -delay 100 ', png_file
    
   


                                        
   
                    
def get_min_max(nc_var_files, cur_stat, p, logger):
    '''Determine the min and max for all lead times for this
       statistic and variable.

       Args:
           nc_var_files:  A list of the netCDF files generated by the MET series 
                          analysis tool that correspond to the variable of interest.
           cur_stat: The current statistic of interest: RMSE, MAE, ODEV, FDEV, ME, or TOTAL.
           p:   The ConfigMaster object, used to retrieve values from the config/param file.
           logger:  The logger to which all log messages are directed.
          
       Returns:
           tuple (vmin, vmax)
               vmin:  The minimum
               vmax:  The maximum
       
    '''
    logger.info("Inside get_min_max")
    out_dir_base = p.opt["OUT_DIR"]
    ncap2_exe = p.opt["NCAP2_EXE"]
    ncdump_exe = p.opt["NCDUMP_EXE"]

    # Initialize the threshold values for min and max.
    VMIN = 999999.
    VMAX = -999999.

    for cur_nc in nc_var_files:
        # Determine the series_F<fhr> subdirectory where this netCDF file
        # resides.
        match = re.match(r'(.*/series_F[0-9]{3})/series_F[0-9]{3}.*nc', cur_nc)
        if match:
            base_nc_dir = match.group(1)
        else:
            logger.error("Cannot determine base directory path for netCDF files")
            logger.error("current netCDF file: " + cur_nc)
            sys.exit()

        min_nc_path = os.path.join(base_nc_dir, 'min.nc')
        max_nc_path = os.path.join(base_nc_dir, 'max.nc')
        nco_min_cmd_parts = [ncap2_exe, ' -v -s ', '"', 'min=min(series_cnt_', cur_stat,')', '" ', cur_nc, ' ', min_nc_path]
        nco_max_cmd_parts = [ncap2_exe, ' -v -s ', '"', 'max=max(series_cnt_', cur_stat,')', '" ', cur_nc, ' ', max_nc_path]
        nco_min_cmd = ''.join(nco_min_cmd_parts)
        nco_max_cmd = ''.join(nco_max_cmd_parts)
        cleanup_min_max_tempfiles('min.nc',p, logger)
        cleanup_min_max_tempfiles('max.nc',p, logger)
        os.system(nco_min_cmd)
        os.system(nco_max_cmd)


        min_txt_path = os.path.join(base_nc_dir, 'min.txt')
        max_txt_path = os.path.join(base_nc_dir, 'max.txt')
        ncdump_min_cmd_parts = [ncdump_exe, ' ', base_nc_dir,'/min.nc > ', min_txt_path]
        ncdump_min_cmd = ''.join(ncdump_min_cmd_parts)
        ncdump_max_cmd_parts = [ncdump_exe,' ', base_nc_dir, '/max.nc > ', max_txt_path]
        ncdump_max_cmd = ''.join(ncdump_max_cmd_parts)
        cleanup_min_max_tempfiles('min.txt',p, logger)
        cleanup_min_max_tempfiles('max.txt',p, logger)
        os.system(ncdump_min_cmd)
        os.system(ncdump_max_cmd)

        # Look for the min and max values in each netCDF file.
        try:
            with open(min_txt_path,'r') as fmin:
                for line in fmin:
                    min_match = re.match(r'\s*min\s*=\s([-+]?\d*\.*\d*)', line)
                    if min_match:
                        cur_min = float(min_match.group(1))
                        if cur_min < VMIN:
                            print("replacing VMIN {} with {}:".format(str(VMIN), str(cur_min) ))
                            VMIN = cur_min
            with open(max_txt_path,'r') as fmax:
                for line in fmax:
                    max_match = re.match(r'\s*max\s*=\s([-+]?\d*\.*\d*)', line)
                    if max_match:
                        cur_max = float(max_match.group(1))
                        if cur_max > VMAX:
                            print("replacing VMAX {} with {}:".format(str(VMAX), str(cur_max) ))
                            VMAX = cur_max
        except IOError as e:
            log.error("ERROR cannot open the min or max text file")



    return VMIN,VMAX

def get_var_ncfiles(cur_var, nc_list, logger):
    ''' Retrieve only the netCDF files corresponding to this statistic
        and variable pairing.

        Args:
            cur_var:   The variable of interest.
            nc_list:  The list of all netCDF files that were generated by
                      the MET utility run_series_analysis.
            logger:  The logger to which all logging messages are sent

        Returns:
            var_ncfiles: A list of netCDF files that
                              correspond to this variable.

    '''
    # Create the regex to retrieve the variable name.
    # The variable is contained in the netCDF file name.
    var_ncfiles = []
    var_regex_parts = [".*series_F[0-9]{3}_", cur_var, "_[0-9a-zA-Z]+.*nc"]
    var_regex = ''.join(var_regex_parts)
    for cur_nc in nc_list:
        # Determine the variable from the filename
        match = re.match(var_regex, cur_nc)
        if match:
            var_ncfiles.append(cur_nc)

    return var_ncfiles

def cleanup_min_max_tempfiles(filename,p,logger):
    '''Clean up all the temporary netCDF and txt
       files used to determine the min and max.

       Args:
           filename: the name of the file to remove
           p: ConfigMaster config file object.
           logger: The logger to which all log messages are 
                   directed.

       Returns:
           None:  removes the specified file in the
                  series_F<fhr> directory.

    '''
    # Retrieve necessary values from the config/param file.
    stat_list = p.opt["STAT_LIST"]
    out_dir_base = p.opt["OUT_DIR"]
    rm_exe = p.opt["RM_EXE"]
   
    for cur_stat in stat_list:
        minmax_nc_path = out_dir_base
        # Iterate through all the series_F<fhr> directories and remove the
        # temporary files created by other runs.
        series_dirs = [os.path.normcase(f) for f in os.listdir(minmax_nc_path)]
        for dir in series_dirs:
            # Create the directory path that includes the series_F<fhr>.
            full_path = os.path.join(minmax_nc_path,dir)

            nc_path = os.path.join(full_path, filename)
            rm_cmd_parts = [rm_exe,' ', nc_path]
            rm_cmd = ''.join(rm_cmd_parts)

            os.system(rm_cmd)


                
       
def retrieve_nc_files(base_dir, logger):
    '''Retrieve all the netCDF files that were created by the MET series analysis binary.
       
       Args:
           base_dir: The base directory where all the series_F<fcst hour> sub-directories
                    are located.  The corresponding variable and statistic files for 
                    these forecast hours are found in these sub-directories.
                   
           logger:  The logger to which all log messages are directed.

       Returns:
           nc_list: A list of the netCDF files (full path) created when the MET series analysis
                   binary was invoked.
    '''
    logger.info("INFO| Retrieving all netCDF files in dir: " + base_dir)
    nc_list = []
    filename_regex = "series_F[0-9]{3}.*nc"

    # Get a list of all the series_F* directories
    series_dir_list = [os.path.normcase(f) for f in os.listdir(base_dir)]
    
    # Iterate through each of these series subdirectories and create a list of
    # all the netCDF files (full file path).
    for dir in series_dir_list:
        full_path = os.path.join(base_dir, dir)
        
        # Get a list of all the netCDF files for this subdirectory.
        nc_files_list = [ f for f in os.listdir(full_path) if os.path.isfile(os.path.join(full_path,f))]
        for cur_nc in nc_files_list:
            match = re.match(filename_regex, cur_nc) 
            if match:
                nc_file = os.path.join(full_path, cur_nc)
                nc_list.append(nc_file)
              
   
    return nc_list    





def retrieve_fhr_tiles(tile_list, file_type, cur_fhr, out_dir, type_regex,logger):            
    ''' Retrieves only the gridded tile files that
        correspond to the type.
        
        Args:
           tile_list:  List of tiles (full filepath).
           file_type : FCST or ANLY
           cur_fhr:  The current forecast hour
           out_dir: The output directory 
           type_regex:  The regex that corresponds to the tile filename for this type
           logger: Logger to which all logging messages are passed.
        
        Returns:
           fhr_tiles (string):  A string of gridded tile names separated by newlines
    '''
    type = file_type.upper() 
    fhr_tiles = '' 
    for cur_tile in tile_list:
       match = re.match(type_regex, cur_tile) 
       if match:
           storm_subdir = match.group(0)
       else:
           logger.error("ERROR: No matching storm id found, exiting...")
           sys.exit()

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
                                   that corresponds to the same lead time
                                   as the input fcst tile. 
    '''
    
    # Derive the ANLY file name from the FCST file.
    anly_from_fcst = re.sub(r'FCST','ANLY', fcst_file)

    if anly_from_fcst in anly_tiles:
        return anly_from_fcst
    else:
        return None



def get_files(filedir, type, filename_regex, cur_fhr, logger):
    ''' Get all the files (with a particular
        naming format) by walking 
        through the directories.
    
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
    file_paths = []
    
    # Walk the tree
    for root, directories, files in os.walk(filedir):
        for filename in files:
            # add it to the list only if it is a match
            # to the specified format
            #prog = re.compile(filename_regex)
            match = re.match(filename_regex, filename)
            if match:
                # Now match based on the current forecast hour
                if type == 'FCST':
                    match_fhr = re.match(r'.*FCST_TILE_F([0-9]{3}).*',match.group())
                elif type == 'ANLY':
                    match_fhr = re.match(r'.*ANLY_TILE_F([0-9]{3}).*',match.group())

                if match_fhr:
                   if match_fhr.group(1) == cur_fhr:
                       # Join the two strings to form the full
                       # filepath.
                       filepath = os.path.join(root,filename)
                       file_paths.append(filepath)
            else:
                continue
    return file_paths

def cleanup_lead_ascii( p, logger):
    ''' Remove any pre-existing FCST and ANLY ASCII files created by previous
        runs of series_by_lead.
        
        Args:
           p      : The ConfigMaster, used to retrieve the parameter values
           logger:  The logger to which all log messages are directed.
     
        Returns:
           None:  Removes any existing FCST and ANLY ASCII files which contains all
                  the forecast and analysis gridded tiles.

        
        
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
    out_dir_base = p.opt["OUT_DIR"]
 
    for fhr in range(fhr_beg, fhr_end + 1, fhr_inc):
        cur_fhr = str(fhr).zfill(3)
        out_dir_parts = [out_dir_base, '/', 'series_F', cur_fhr]
        out_dir = ''.join(out_dir_parts)    
          
        for root,directories,files in os.walk(out_dir):
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
    analysis_by_lead_time(p, logger)

