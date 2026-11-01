"""Authoritative warm presentation palette, shared by native and browser builds."""
PALETTE={
 'ground':'#fbf7ee','surface':'#fffcf5','tint':'#f2e8d3','line':'#d9ccb6',
 'text':'#332c22','muted':'#74644d','accent':'#855f22','gold':'#835e1c',
 'secondary':'#646b43','success':'#536746','danger':'#9d4437',
}
def rgb(name):
 value=PALETTE[name].lstrip('#');return tuple(int(value[i:i+2],16) for i in (0,2,4))
BG=rgb('ground');FG=rgb('text');DIM=rgb('muted');GRID=rgb('line')
ACCENT=rgb('accent');AMBER=rgb('gold');SECONDARY=rgb('secondary');GREEN=rgb('success')
