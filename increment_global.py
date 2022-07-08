import argparse

from larpix import Configuration_v2

def main(*files, global_threshold_inc=0, dry_run=False, **kwargs):
        for file in files:
                config = Configuration_v2()
                config.load(file)
                if config.threshold_global + global_threshold_inc >= 255:
                        config.threshold_global = 255
                else: 
                        config.threshold_global += global_threshold_inc
                if not dry_run:
                        config.write(file, force=True)
                else:
                        print('loaded {}'.format(file))
                        print('set global threshold to {}'.format(config.threshold_global))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('input_files', nargs='+', help='''files to modify''')
    parser.add_argument('--inc', type=int, default=0, help='''amount to change global threshold by''')
    parser.add_argument('--dry_run', action='store_true', help='''print stuff but don't do anything''')
    args = parser.parse_args()
    
    main(
        *args.input_files,
        global_threshold_inc=args.inc,
        dry_run=args.dry_run
    )
