def unique_channel_id_2_str(unique_id):
    return (unique_id//(256*256*64)).astype(int).astype(str) \
        + '-' + ((unique_id//(256*64))%256).astype(int).astype(str) \
        + '-' + ((unique_id//64)%256).astype(int).astype(str) \
        + '-' + (unique_id%64).astype(int).astype(str)

def unique_channel_id(channel):
    return ((channel['io_group'].astype(int)*256 + channel['io_channel'].astype(int))*256 \
            + channel['chip_id'].astype(int))*64 + channel['channel_id'].astype(int)

def unique_chip_id(channel):
    return (channel['io_group'].astype(int)*256 + channel['io_channel'].astype(int))*256 + \
           channel['chip_id'].astype(int)