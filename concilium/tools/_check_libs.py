import importlib.util
for lib in ['plotly','matplotlib','kaleido','highcharts_gantt','PIL','cairosvg']:
    found = importlib.util.find_spec(lib)
    print(f"{lib}: {'OK' if found else 'MISSING'}")
