# A.B.P. Always Be Proxying
## Generate MtG proxy sheets from mythicspoiler.com

`abp.py` takes a text file specifying a list of MtG cards and generates a set of 3x3 PDF sheets.

Unless otherwise specified, the source images are pulled from [mythicspoiler.com](http://mythicspoiler.com).
```
$ python abp.py cards.txt
./Sheet01.pdf
```

## cards.txt
```
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

```

## Sheet01.pdf
![alt text](https://github.com/RobRuana/abp/raw/master/example_Sheet01_134.26dpi.png "Example output")

## Installation

```
pip install -r requirements.txt
```

If it fails with the following error message:
```
ValueError: jpeg is required unless explicitly disabled using --disable-jpeg, aborting
```

Try install ``libjpeg`` (or equivalent for your OS)
```
# on OS X with homebrew
brew install libjpeg
```


