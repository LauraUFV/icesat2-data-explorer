# Third-party software and data services

The plugin source is licensed under GPL-2.0-or-later. Third-party packages and services retain their own licenses. They are **not vendored in this plugin ZIP** unless explicitly stated.

- **QGIS** - GPL-2.0-or-later; runtime GIS platform.
- **SlideRule Python client 5.5.0** - BSD-3-Clause; installed on demand into user-managed plugin storage.
- **SlideRule Earth services** - remote service used to subset/process ICESat-2 products.
- **h5py** - BSD-3-Clause; installed on demand into plugin-managed storage for local HDF5 conversion.
- **pyTMD 3.0.9** - MIT; optional, installed into an isolated environment for tidal prediction.
- **GOT4.10c** - downloaded at runtime through the pyTMD model workflow; not bundled with the plugin. Users are responsible for following the model/data provider's terms and citation guidance.
- **NASA/NSIDC ICESat-2 data** - accessed remotely; scientific datasets retain their provider citation requirements.

The plugin installers intentionally avoid upgrading the QGIS scientific Python stack when installing SlideRule or h5py.
