Hudsucker Proxy Generator
=========================

Generate MtG proxy sheets from mythicspoiler.com & other sites
--------------------------------------------------------------

``hudsucker`` takes a text file specifying a list of MtG cards and generates a set of 3x3 PDF sheets.

Unless otherwise specified, the source images are pulled from `mythicspoiler.com <http://mythicspoiler.com>`_.

::

    $ hudsucker cards.txt
    ./cards01.pdf


cards.txt
---------

::

    # Example input file, comments and blank lines are supported

    # Cards names are listed one per line, misspellings are okay
    Pia Nalaar              # Inline comments are also supported
    Saheeli's Artistry      # Spaces, capitals, and punctuation are fine

    # For multiples of the same card, list them multiple times
    Strip Mine
    Strip Mine

    # The page for the card can be specified
    http://mythicspoiler.com/kld/cards/wispweaverangel.html

    # Or the image file can be listed explicitly
    http://mythicspoiler.com/kld/cards/trinketmastercraft.jpg
    http://www.mythicspoiler.com/kld/cards/gontilordofluxury.jpg

    # Sites other than mythicspoiler.com can be specified
    # A best attempt will be made to determine the card image
    http://magiccards.info/vma/en/4.html # Black Lotus

    # Image files from any site can also be listed explicitly
    http://magiccards.info/scans/en/vma/1.jpg # Ancestral Recall


cards01.pdf
-----------

.. image:: https://github.com/RobRuana/hudsucker/raw/master/example_Sheet01_134.26dpi.png
   :alt: Example output


Installation
------------

::

    pip install hudsucker


If it fails with the following error message::

    ValueError: jpeg is required unless explicitly disabled using --disable-jpeg, aborting


Try installing ``libjpeg`` (or equivalent for your OS)::

    # on OS X with homebrew
    brew install libjpeg


Help
----

::

    usage: hudsucker [-h] [-v] [-b N] [-o DIR] [-p N] [-q N] [-s URL] [-c DIR]
                     [-n] [-r]
                     FILE [FILE ...]

    Hudsucker Proxy Generator - generate MtG proxy sheets

    positional arguments:
      FILE                  each line of FILE should be a MtG card name, or a url

    optional arguments:
      -h, --help            show this help message and exit
      -v, --verbose         print verbose details

    proxy sheet options:
      -b N, --border N      border width in inches, defaults to 0.072
      -o DIR, --output DIR  output dir, defaults to current dir
      -p N, --resolution N  print resolution of output PDF, defaults to 600
      -q N, --quality N     quality to use for JPEG encoding, defaults to 95
      -s URL, --site URL    site to search for card images, defaults to
                            mythicspoiler.com

    caching options:
      NOTE: Careful turning off cache, search engines may ban your IP

      -c DIR, --cache DIR   cache dir, defaults to hudsucker_cache
      -n, --no-cache        don't cache any downloaded files
      -r, --refresh         force refresh of any cached downloads


Contributing
------------

Report bugs or make pull requests on `GitHub <https://github.com/RobRuana/hudsucker>`_.

