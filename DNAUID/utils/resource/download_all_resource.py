async def download_all_resource():
    from ...utils.name_convert import refresh_name_convert

    await refresh_name_convert()
