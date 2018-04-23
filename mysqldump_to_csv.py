#!/usr/bin/env python
import fileinput
import csv
import os
import re
import sys

# This prevents prematurely closed pipes from raising
# an exception in Python
from signal import signal, SIGPIPE, SIG_DFL

from collections import defaultdict

import errno

signal(SIGPIPE, SIG_DFL)

# allow large content in the dump
csv.field_size_limit(sys.maxsize)

OUTDIR_PARAM = '--out-dir='
COL_NAMES_PARAM = '--col-names'
file_cache = defaultdict()


def is_insert(line):
    """
    Returns true if the line begins a SQL insert statement.
    """
    return line.startswith('INSERT INTO') or False


def get_values(line):
    """
    Returns the portion of an INSERT statement containing values
    """
    capture = re.match(r'^INSERT\s+INTO\s+`?(.*?)`?\s*(\(.*?\))?\s*VALUES\s*(\(.*?$)', line)
    if capture is None:
        return None
    return capture.groups()[2]


def get_table_filename(line, output_dir):
    """
    Returns the table destination for the INSERT statement
    """
    capture = re.match(r'^INSERT\s+INTO\s+`?(.*?)`?\s', line)
    if capture is None:
        return None

    return os.path.join(output_dir, capture.groups()[0] + '.csv')


def get_column_names(line):
    capture = re.match(r'^INSERT\s+INTO\s+`?(.*?)`?\s*(\(.*?\))\s*VALUES.*$', line)
    if capture is None:
        return None

    cols = []
    for value in capture.groups()[1].strip('()').split(','):
        cols.append(value.strip('` '))
    return cols


def handle_col_names(line, outfile):
    cols = get_column_names(line)
    if cols is None:
        if not handle_col_names.col_error_printed:
            handle_col_names.col_error_printed = True
            print 'Column names were not found in at least one INSERT statement, and can not be recorderd.'
            print 'Use --complete-insert with mysqldump to have column names in your dumped SQL.'
        return
    if outfile not in handle_col_names.cols_written:
        get_writer(outfile).writerow(cols)
        handle_col_names.cols_written.add(outfile)
handle_col_names.col_error_printed = False
handle_col_names.cols_written = set()


def values_sanity_check(values):
    """
    Ensures that values from the INSERT statement meet basic checks.
    """
    assert values
    assert values[0] == '('
    # Assertions have not been raised
    return True


def parse_values(values, outfile):
    """
    Given a file handle and the raw values from a MySQL INSERT
    statement, write the equivalent CSV to the file
    """
    cleaned_up_values = re.sub(
        r'\)\s*,\s*\(',
        '\n',
        values.strip('()')
    ).split('\n')

    reader = csv.reader(cleaned_up_values, delimiter=',',
                        doublequote=False,
                        escapechar='\\',
                        quotechar="'",
                        strict=True
    )

    writer = get_writer(outfile)

    for reader_row in reader:
        latest_row = []
        for column in reader_row:
            # If our current string is empty...
            if len(column) == 0 or column == 'NULL':
                latest_row.append(chr(0))
                continue
            # Add our column to the row we're working on.
            latest_row.append(column)
        writer.writerow(latest_row)


def get_writer(outfile):
    if outfile is sys.stdout:
        writer = csv.writer(outfile,
                            quoting=csv.QUOTE_MINIMAL,
                            doublequote=False,
                            escapechar='"'
                            )
    else:
        writer = csv.writer(file_cache.setdefault(outfile, open(outfile, 'wb')),
                            quoting=csv.QUOTE_MINIMAL,
                            doublequote=False,
                            escapechar='"'
                            )
    return writer


def find_and_remove_param(args, param):
    for i in xrange(len(args)):
        if args[i].startswith(param):
            return args.pop(i)
    return None


def main():
    """
    Parse arguments and start the program
    """
    write_col_names = None
    input_files = None
    output_dir = None
    if len(sys.argv) > 1:
        output_dir_param = find_and_remove_param(sys.argv, OUTDIR_PARAM)
        if output_dir_param is not None:
            output_dir = output_dir_param[len(OUTDIR_PARAM):]
            try:
                os.makedirs(output_dir)
            except OSError as e:
                # If the director already exists, great.
                # Otherwise, raise the error.
                if e.errno != errno.EEXIST:
                    raise

        col_names_param = find_and_remove_param(sys.argv, COL_NAMES_PARAM)
        write_col_names = col_names_param is not None

    # Iterate over all lines in all files
    # listed in sys.argv[1:]
    # or stdin if no args given.
    try:
        for line in fileinput.input(input_files):
            # Look for an INSERT statement and parse it.
            if is_insert(line):
                table = get_table_filename(line, output_dir) if output_dir else None
                if write_col_names:
                    handle_col_names(line, table or sys.stdout)
                values = get_values(line)
                if values_sanity_check(values):
                    parse_values(values, table or sys.stdout)

        for files in file_cache.itervalues():
            files.close()

    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
