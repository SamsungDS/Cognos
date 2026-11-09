# Writing a new RAS Adapter

A new RAS adapter can support a new device type. The ras adapter has to conform to both svk logic interface and RAS adapter specification. For the RAS feature to detect and load a new RAS adapter on initialization, it has to be in the specific folder defined below,

'''
<RAS_INSTALLATION_DIR>/<ADAPTER_NAME>/lib64/lib<ADAPTER_NAME>.so
'''

The default `RAS_INSTALATION_DIR` is `/usr/local/svk/feature_modules/ras/`