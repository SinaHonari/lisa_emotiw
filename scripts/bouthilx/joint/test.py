#from pylearn2.utils.shell import run_shell_command
from gen_yaml import generate_params, write_files

#import contest_dataset

import traceback
import sys
import os
import argparse

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out",required=True,help="The name of the yaml file produced")
    parser.add_argument("--template",required=True,help="YAML template")
    parser.add_argument("--hparams",required=True,help="Hyper-parameters configuration")
    parser.add_argument("--force",action='store_true',help="Force to overwrite the old yaml file produced")
    options = parser.parse_args()

    out = options.out
    template = options.template
    hparams = options.hparams
    force = options.force
    
    print options

    # Generates a list of hyper-parameter names and a list of 
    # hyper-parameter values
    hpnames, hpvalues = generate_params(hparamfile=hparams,
                                        generate="uniform",
                                        search_mode="fix-grid-search")

    # Writes template with each hyper-parameter settings in  
    # succesive files and returns the name of the files
    files = write_files(template="".join(open(template,"r")),hpnames=hpnames,
                        hpvalues=hpvalues,save_path=out,force=force)

    print_error_message("errors\n",out,"w")
    from pylearn2.utils import serial

    for i in xrange(0,len(files)):
        f = files[i]
        try:
           serial.load_train_file(f).main_loop()
        except BaseException as e:
            print traceback.format_exc()
            print e
            print_error_message("%s : %s\n" % (f,str(e)),out)

def print_error_message(message,out,mode='a'):
    curdir = os.getcwd()
    new_path = "/".join(out.split("/")[:-1])
    print new_path
    os.chdir(new_path)
    error = open("errors.log",mode)
    error.write(message)
    error.close()
    os.chdir(curdir)
    pass

if __name__ == "__main__":
    main()
