"""Export only used Unicode mappings, retaining the original outlines/metrics."""
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools import subset

def export_subset(source,target,unicodes):
    font=TTFont(source)
    options=subset.Options();options.recalc_timestamp=False
    subsetter=subset.Subsetter(options=options);subsetter.populate(unicodes=set(unicodes)|{0x20,0x3000});subsetter.subset(font)
    font.save(target);font.close()
