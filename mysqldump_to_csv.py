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
    return line.partition('` VALUES ')[2]


def get_table_filename(line, output_dir):
    """
    Returns the table destination for the INSERT statement
    """
    capture = re.match(r'^INSERT\s+INTO\s+`?(.*?)`?\s', line)
    if capture is None:
        return None

    return os.path.join(output_dir, capture.groups()[0] + '.csv')


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
    latest_row = []

    reader = csv.reader([values], delimiter=',',
                        doublequote=False,
                        escapechar='\\',
                        quotechar="'",
                        strict=True
    )

    if outfile is sys.stdout:
        writer = csv.writer(outfile,
                            quoting=csv.QUOTE_MINIMAL,
                            doublequote=False,
                            escapechar='\\'
        )
    else:
        writer = csv.writer(file_cache.setdefault(outfile, open(outfile, 'wb')),
                            quoting=csv.QUOTE_MINIMAL,
                            doublequote=False,
                            escapechar='\\'
        )

    for reader_row in reader:
        for column in reader_row:
            # If our current string is empty...
            if len(column) == 0 or column == 'NULL':
                latest_row.append(chr(0))
                continue
            # If our string starts with an open paren
            if column[0] == "(":
                # Assume that this column does not begin
                # a new row.
                new_row = False
                # If we've been filling out a row
                if len(latest_row) > 0:
                    # Check if the previous entry ended in
                    # a close paren. If so, the row we've
                    # been filling out has been COMPLETED
                    # as:
                    #    1) the previous entry ended in a )
                    #    2) the current entry starts with a (
                    if latest_row[-1][-1] == ")":
                        # Remove the close paren.
                        latest_row[-1] = latest_row[-1][:-1]
                        new_row = True
                # If we've found a new row, write it out
                # and begin our new one
                if new_row:
                    writer.writerow(latest_row)
                    latest_row = []
                # If we're beginning a new row, eliminate the
                # opening parentheses.
                if len(latest_row) == 0:
                    column = column[1:]
            # Add our column to the row we're working on.
            latest_row.append(column)
        # At the end of an INSERT statement, we'll
        # have the semicolon.
        # Make sure to remove the semicolon and
        # the close paren.
        if latest_row[-1][-2:] == ");":
            latest_row[-1] = latest_row[-1][:-2]
            writer.writerow(latest_row)


def main():
    """
    Parse arguments and start the program
    """

    if len(sys.argv) > 1 and sys.argv[1].startswith(OUTDIR_PARAM):
        input_files = sys.argv[2:]
        output_dir = sys.argv[1][len(OUTDIR_PARAM):]
        try:
            os.makedirs(output_dir)
        except OSError as e:
            # If the director already exists, great.
            # Otherwise, raise the error.
            if e.errno != errno.EEXIST:
                raise
    else:
        input_files = None  # default behavior for fileinput
        output_dir = None

    # Iterate over all lines in all files
    # listed in sys.argv[1:]
    # or stdin if no args given.
    try:
        for line in fileinput.input(input_files):
            # Look for an INSERT statement and parse it.
            if is_insert(line):
                table = get_table_filename(line, output_dir) if output_dir else None
                values = get_values(line)
                if values_sanity_check(values):
                    parse_values(values, table or sys.stdout)

        for files in file_cache.itervalues():
            files.close()

    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
