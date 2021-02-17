#! /bin/bash

pip3 install matplotlib
pip3 install scipy

basedir=$(dirname "$0")
work_dir=$basedir/../..

# run manage externals to obtain METcalcpy
${work_dir}/METplus/manage_externals/checkout_externals -e ${work_dir}/METplus/ci/parm/Externals_metplotpy.cfg

pip3 install ${work_dir}/METplotpy
