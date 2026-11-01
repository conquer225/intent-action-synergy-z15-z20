import vitis


WORKSPACE = r"D:\ican\guardianloop-vitis-2025_2"
APPLICATION = "guardianloop_eeg_dma_test_2025_2"


client = vitis.create_client()
try:
    client.set_workspace(path=WORKSPACE)
    application = client.get_component(name=APPLICATION)
    if application is None:
        raise RuntimeError(f"Application component not found: {APPLICATION}")
    print("Building GuardianLoop Cortex-A9 application...")
    result = application.build()
    print(result)
    if result != 0:
        raise RuntimeError(f"Application build failed with status {result}")
finally:
    vitis.dispose()
