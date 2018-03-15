#!/usr/bin/env python
import fileinput
import csv
import sys

# This prevents prematurely closed pipes from raising
# an exception in Python
from signal import signal, SIGPIPE, SIG_DFL
signal(SIGPIPE, SIG_DFL)

# allow large content in the dump
csv.field_size_limit(sys.maxsize)

def is_insert(line):
    """
    Returns true if the line begins a SQL insert statement.
    """
    return line.startswith('INSERT INTO') or False

def get_insert_values(line):
    """
    Returns the portion of an INSERT statement containing values
    """
    return line.partition('` VALUES ')[2]

def get_create_keys(fileinput):
    """
    Returns all of the value keys within the CREATE statement.
    """
    reading_keys = False
    keys = []
    for line in fileinput:
        if line.startswith('CREATE TABLE'):
            reading_keys = True
            continue

        elif line.startswith('  PRIMARY KEY') or line.startswith('  KEY'):
            reading_keys = False
            break

        if reading_keys:
            new_key = line.partition("`")[2].partition("`")[0]
            keys.append(new_key)
    return keys


def values_sanity_check(values):
    """
    Ensures that values from the INSERT statement meet basic checks.
    """
    assert values
    assert values[0] == '('
    # Assertions have not been raised
    return True

def write_keys(keys, outfile):
    """
    Given a file handle and the raw keys from a MySQL CREATE
    statement, write the equivalent CSV to the file
    """
    writer = csv.writer(outfile, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(keys)

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

    writer = csv.writer(outfile, quoting=csv.QUOTE_MINIMAL)
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
    # Iterate over all lines in all files
    # listed in sys.argv[1:]
    # or stdin if no args given.
    inp = fileinput.input()
    keys = get_create_keys(inp)
    write_keys(keys, sys.stdout)
    try:
        for line in inp:
            # Look for an INSERT statement and parse it.
            if is_insert(line):
                values = get_insert_values(line)
                if values_sanity_check(values):
                    parse_values(values, sys.stdout)
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    main()
