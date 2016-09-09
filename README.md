# A.B.P. Always Be Proxying
## Generate MtG proxy sheets from mythicspoiler.com

`abp.py` takes a text file specifying a list of MtG cards and generates a set of `*.png` images with the cards in a 3x3 layout. The output files will have the correct print DPI in the filename: `Sheet01_134.26dpi.png`.

Unless otherwise specified, the source images are pulled from [mythicspoiler.com](mythicspoiler.com).
```
$ python abp.py cards.txt
./Sheet01_134.26dpi.png
```

## cards.txt
```
# Example input file, comments and blank lines are fine

# Cards names can be listed directly, one per line
Pia Nalaar              # In-line comments are also supported
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

## Sheet01_134.26dpi.png
![alt text](https://github.com/RobRuana/abp/raw/master/example_Sheet01_134.26dpi.png "Example output")

