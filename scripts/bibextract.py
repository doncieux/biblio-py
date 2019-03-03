#!/usr/bin/env python
'''
Script to read an *.aux file generated by latex and extract all the references to a
new bibtex file

'''
import sys
import re
import os
import subprocess as sub

################################################################################
# CUSTOMIZE THESE VARIABLES if needed
dumpfile = os.getenv('BIBDB')
# *******************************************************************************
encoding = 'utf8'
from yapbib.version import VERSION
import yapbib.biblist as biblist

rex_bibfile = re.compile(r'\\bibliography\{([^}]*)\}')
rex_bibdata = re.compile(r'\\bibdata\{([^}]*)\}')
rex_texcite = re.compile(
    r'\\(?:no)?cite(?:alt|p|t|author|year)?[\*]?(?:\[[^]]*\]){0,2}\{([^}]*)\}', re.M)
rex_auxcite = re.compile(r'\\citation{([^}]*)}')
rex_auxinput = re.compile(r'\\@input{([^}]+)}')

# Para biber y biblatex
rex_auxcite = re.compile(r'\\abx@aux@cite{([^}]*)}')


def get_strng_field(k):
  """Parse arguments of the form string:field"""
  valor = k.split(':')
  if len(valor) == 1:
    ff = []
    ss = valor[0]
  elif len(valor) == 2:
    if valor[0] == '': ss = '*'  # Search all strings
    else: ss = valor[0]
    if valor[1] == '': ff = []  # Search in all fields
    else: ff = valor[1].split(':')
  return ss, ff


def parse_texfile(texfile):
  reflist = []
  fi = open(texfile); s = fi.readlines(); fi.close()
  bib = None
  for line in s:
    line = line[:line.find('%')]
    # Find the \cite commands
    for m in rex_texcite.finditer(line):
      if m is not None: reflist.extend(m.group(1).split(','))
    # Find the bibliography command
    m = rex_bibfile.search(line)
    if m is not None: bib = m.group(1)
  return bib, make_unique(reflist)


def parse_auxfile(auxfile):
  """Parse an auxfile (recursing if necessary) and return citation list"""
  reflist = []
  fi = open(auxfile); s = fi.readlines(); fi.close()
  bib = None
  for line in s:
    m1 = rex_auxinput.search(line)  # Search input of aux file
    if m1: reflist.extend(parse_auxfile(m1.group(1))[1])
    m = rex_auxcite.search(line)   # Seach for citations
    # if m != None:  reflist.append(m.group(1))
    if m is not None:
      reflist.extend(m.group(1).split(','))

    # Find the bibdata (file)
    m = rex_bibdata.search(line)
    if m is not None: bib = m.group(1)
  return bib, make_unique(reflist)


def make_unique(lista):
  """Simple (may fail if lista is not a list) unique function"""
  seen = []
  return list(c for c in lista if not (c in seen or seen.append(c)))


def remove_fields(item, cond):
  ff, ty = get_strng_field(cond)
  if item.get_field('_type') in [t.lower() for t in ty] or ty == []:
    if item.get_field(ff) is not None:
      del(item[ff])


def find_bibfile(fbib):
  """
  Find the bibtex file referred to in the source file.
  Currently it searches first in the current directory.
  If it fails it uses kpsewhich
  Arguments:
  - `fbib`: list of base of filename (with no path)
  """
  ffobib = []
  for filebib in fbib.split(','):
    if filebib is None: return None
    fobib = filebib + '.bib'
    if not os.path.exists(fobib):
      fobib = sub.Popen(['kpsewhich', filebib + '.bib'], stdout=sub.PIPE).communicate()[0].strip()
    ffobib.append(fobib)
  return ffobib


def main():
  import optparse
  usage = """usage: %prog [options] datafile1 [datafile2 ...]
  Extracts a BibTeX database according to an aux or tex file.
  Keeps only those items that are cited

  DESCRIPTION It reads an *.aux file as produced by LaTeX or a *.tex file directly
       and writes to standard output a bibtex file containing exactly the
       bibtex entries refereed in the aux file.

  NOTE:  If the environment variable BIBDB is set, this is used as bibliography database

  ************************************************************
  USE %prog --help for details
  ************************************************************
  """

  parser = optparse.OptionParser(usage, version=" %prog with biblio-py-{0}".format(VERSION))

  parser.add_option(
      "-d",
      "--database",
      action='append',
      type='string',
      help="Database to use, default: %s. May be used more than once" %
      (dumpfile))

  parser.add_option("-l", "--list", action="store_true", dest="list",
                    default=False, help="List cited keys to stdout (screen)")

  parser.add_option("-o", "--output", default=None, help="Output file. Use '-' for stdout (screen)")

  parser.add_option(
      "",
      "--remove-common",
      action="store_true",
      default=False,
      help="Remove \"url from articles\", \"doi, issn, month and abstracts from everything\"")

  parser.add_option(
      "",
      "--remove-fields",
      action='append',
      type='string',
      help="Remove fields from types. Notations is \"field:type1,type2,..,typen\" to remove field from these types (for instance ARTICLES and BOOKS but not for INPROCEEDINGS), Use \"field\" (with no \":\") for removing the field for all types. It can be used more than once for removing several fields")

  parser.add_option("-v", "--verbose", action="store_true", dest="verbose",
                    default=True, help="Give some informational messages. [default]")

  parser.add_option(
      "-q",
      "--quiet",
      action="store_false",
      dest="verbose",
      help="Suppress some messages.")

  (op, args) = parser.parse_args()

  if len(args) < 1:
    parser.error("Incorrect number of arguments. You have to give a source filename")

  for fname in args:                    # Read the source file
    if fname.endswith('tex'):
      dbf, cit = parse_texfile(fname)
    elif fname.endswith('aux'):
      dbf, cit = parse_auxfile(fname)
    else:
      parser.error('Incorrect argument "%s"' % (fname))
    if dbf is not None: dbf = find_bibfile(dbf)

  # Determine the database
  dbfiles = []
  if op.database is not None:               # command-line option overrides others options
    dbfiles = op.database
  elif dbf is not None:                     # Then, bibliography from source file
    dbfiles = dbf
  elif dumpfile is not None:
    dbfiles += [dumpfile]
  else:
    parser.error('No Database found')

  # Read the database(s)
  b = biblist.BibList()
  for fname in dbfiles:
    if op.verbose: print('# Loading database %s ...' % (fname))
    failed = False
    if '.dmp' in fname:
      try: b.load(fname)
      except BaseException: failed = True
    elif '.bib' in fname:
      try: b.import_bibtex(fname, normalize=False)
      except BaseException: failed = True
    else: failed = True

    if failed:
      mensaje = 'Database file %s not found or failed to load.'
      mensaje += ' Set the name as an option or set the environment variable BIBDB' % (fname)
      parser.error(mensaje)

  if op.output is None: output = os.path.splitext(args[0])[0] + '.bib'
  else: output = op.output

  # Set fields to remove
  rem = []
  if op.remove_common:
    rem = rem + ['url:article', 'issn', 'doi', 'month', 'abstract']
  if op.remove_fields is not None:
    rem = rem + op.remove_fields

########################################################################
  if op.list:
    print('\n'.join(sorted(cit)))

  bout = biblist.BibList()
  # All keys from databases
  citekeys = dict([(b.get_item(k).get_field('_code'), k) for k in b.ListItems])

  for k in cit:
    if k in list(citekeys.keys()):
      if citekeys[k] in b.ListItems:
        item = b.get_item(citekeys[k])
        if rem != []:
          for cond in rem: remove_fields(item, cond)
        bout.add_item(item, k)
    else:
      print('# Warning: %s not found in database' % (k))
  mensaje = '# created with:  %s\n' % (' '.join(sys.argv))
  # print(type(bout.to_bibtex()))
  # print(bout.to_bibtex())
  fi = open(output, encoding='utf-8', mode='w'); fi.write(mensaje + bout.to_bibtex()); fi.close()
  if op.verbose: print('Items saved to %s' % (output))


if __name__ == "__main__":
  main()


# Local Variables:
# tab-width: 2
# END:
