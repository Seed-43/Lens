function generate_po()
{
    cd po
    git pull https://hosted.weblate.org/git/lens/lens/default
    >lens.pot
    for file in ../data/org.github.seed43.lens.gschema.xml ../data/*.in ../data/ui/*.blp ../lens/*.py ../lens/services/*.py ../lens/types/*.py ../lens/widgets/*.py
    do
        xgettext --add-comments --keyword=_ --keyword=C_:1c,2 --from-code=UTF-8 -j $file -o lens.pot
    done
    >LINGUAS
    for po in *.po
    do
        msgmerge -N $po lens.pot > /tmp/$$language_new.po
        mv /tmp/$$language_new.po $po
        language=${po%.po}
        echo $language >>LINGUAS
    done
}

generate_po
