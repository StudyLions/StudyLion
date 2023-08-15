from data import Registry, Table


class VideoData(Registry):
    video_channels = Table('video_channels')
    video_exempt_roles = Table('video_exempt_roles')
    video_blacklist_durations = Table('studyban_durations')
