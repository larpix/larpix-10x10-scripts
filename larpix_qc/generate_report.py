#!/usr/bin/env python3
"""
Report generation script.
To generate the HTML file:

pandoc -s -f markdown -t html5 -o report.html -c report_style.css report.md

"""

import argparse
import json

_default_leakage_threshold = 2000

def main(log_qc,
         leakage_threshold=_default_leakage_threshold):
    with open(log_qc,'r') as log_qc_file:
        json_log = json.load(log_qc_file)

    report_file = open('report.md', 'w')
    print("# Quality control report", file=report_file)

    for tile in json_log.keys():
        print("## Tile %s" % tile, file=report_file)
        for stage in json_log[tile]:
            print("### %s stage" % stage, file=report_file)
            for test in json_log[tile][stage]:
                print("#### %s" % test, file=report_file)
                print("\nLeakage channels above %i Hz\n" % leakage_threshold,
                      file=report_file)
                if "Leakage" in test:
                    print("""| Chip | Channel | Leakage Rate [Hz] |
| --- | --- | --- |""", file=report_file)
                    for chip_key in json_log[tile][stage][test]:
                        for channel in json_log[tile][stage][test][chip_key]:
                            leakage_rate = json_log[tile][stage][test][chip_key][channel]
                            if leakage_rate > leakage_threshold:
                                print("| %s | %s | %.2f |" % (chip_key, channel, leakage_rate),
                                    file=report_file)
                    print("\n![](leakage.png)\n", file=report_file)
    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_qc',
                        type=str,
                        help='''JSON QC log file''')
    parser.add_argument('--leakage_threshold',
                        default=_default_leakage_threshold,
                        type=str,
                        help='''Leakage rate threshold''')
    args = parser.parse_args()
    c = main(**vars(args))