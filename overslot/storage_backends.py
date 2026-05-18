from storages.backends.s3boto3 import S3ManifestStaticStorage


class LenientS3ManifestStaticStorage(S3ManifestStaticStorage):
    """
    S3 manifest storage that does not raise when staticfiles.json is missing a path.

    Stale CDN copies of staticfiles.json, partial collectstatic runs, or upload races can leave
    the manifest incomplete while objects (or finders) still match. Django's default
    manifest_strict mode then 500s on {% static %} for any omitted key; this falls back to
    computing the hashed name at runtime instead.
    """

    manifest_strict = False
