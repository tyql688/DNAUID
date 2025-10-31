from gsuid_core.utils.download_resource.download_core import download_all_file


async def download_all_resource():

    await download_all_file(
        "DNAUID",
        {},
    )
