# coding: utf-8

import click
import os
import hashlib
import re
import sys
from pathlib import Path


class FileAttr(object):
    def __init__(self, path):
        self.path = path
        self.md5sum = ""
        self.sh256sum = ""
        self.size = 0


def parse_release_block_title_line(line):
    if line.startswith("MD5Sum:"):
        return True, "md5sum"
    elif line.startswith("SHA256:"):
        return True, "sh256sum"
    else:
        return False, ""


def dist_attrs(dist_dir):
    """ Parse file attributes in Release file """
    attrs = {}

    for release in Path(dist_dir).rglob('Release'):
        with open(release.as_posix(), "rt") as f:
            in_block = False
            attr_name = ""

            for line in f.readlines():
                if in_block:
                    if not line.startswith(" "):
                        in_block, attr_name = parse_release_block_title_line(line)
                        continue
                    checksum, size, rname = line.split()
                    path = os.path.join(dist_dir, rname)

                    attr = attrs.get(path)
                    if attr is None:
                        attr = FileAttr(path)
                    attr.size = int(size)
                    setattr(attr, attr_name, checksum)
                    attrs[path] = attr

                elif not line.startswith(" "):
                    in_block, attr_name = parse_release_block_title_line(line)
                    continue

    return attrs


def pkg_attrs(pkg_desc_path):
    with open(pkg_desc_path, "rt") as f:
        attrs = {}
        last_key = None
        for line in f.readlines():
            line = line.rstrip('\n')
            if len(line.strip()) == 0:
                yield attrs
                attrs = {}
                last_key = None
            elif line.startswith(" "):  # last line continue
                if last_key is None:
                    raise ValueError
                attrs[last_key] += line
            else:
                sep_index = line.find(":")
                if sep_index < 0:
                    raise ValueError
                last_key = line[:sep_index]
                attrs[last_key] = line[sep_index + 2:]  # skip : and a space


def pool_attrs(dist_dir, pool_dir):
    """ Parse attributes in Packages file"""
    attrs = {}
    pool_parent_dir = os.path.dirname(pool_dir)

    for root, _, files in os.walk(dist_dir):
        for filename in files:
            if filename != "Packages":
                continue
            for pkgattr in pkg_attrs(os.path.join(root, filename)):
                name = pkgattr["Filename"]
                if name.startswith("pool/"):
                    path = os.path.join(pool_parent_dir, name)

                    attr = FileAttr(path)
                    attr.size = int(pkgattr.get("Size", "0"))
                    attr.md5sum = pkgattr.get("MD5sum", "")
                    attr.sh256sum = pkgattr.get("SHA256", "")

                    attrs[path] = attr
    return attrs


def is_checksum_correct(filepath, attr):
    s = os.stat(filepath)
    if attr.size != s.st_size:
        print(filepath, "expected size: {}, but {}".format(attr.size, s.st_size))
        return False

    if len(attr.md5sum) != 0:
        m = hashlib.md5()
        expected_checksum = attr.md5sum
    elif len(attr.sh256sum) != 0:
        m = hashlib.sha256()
        expected_checksum = attr.sh256sum
    else:
        return True

    with open(filepath, "rb") as f:
        while True:
            data = f.read(1024 * 1024)
            if not data:
                break

            m.update(data)
        checksum = m.hexdigest()

    if checksum != expected_checksum:
        print(filepath, "expected checksum: {}, but {}".format(expected_checksum, checksum))
        return False

    return True


def bad_files_in_dir(dirpath, attrs):
    for root, _, files in os.walk(dirpath):
        for filename in files:
            filepath = os.path.join(root, filename)
            if filepath in attrs:
                if not is_checksum_correct(filepath, attrs[filepath]):
                    yield filepath


def bad_files_in_mirror(mirror_dir):
    dist_root = os.path.join(mirror_dir, "dists")
    walker = os.walk(dist_root)
    _, subdirs, _ = next(walker)

    dist_dirs = [os.path.join(dist_root, subdir) for subdir in subdirs]
    pool_dir = os.path.join(mirror_dir, "pool")

    for dist_dir in dist_dirs:
        click.echo("checking %s ..." % dist_dir)
        yield from bad_files_in_dir(dist_dir, dist_attrs(dist_dir))
        yield from bad_files_in_dir(pool_dir, pool_attrs(dist_dir, pool_dir))


def all_mirrors(sites_dir):
    walker = os.walk(sites_dir)
    _, sites, _ = next(walker)
    for site in sites:
        walker = os.walk(os.path.join(sites_dir, site))
        sitepath, releases, _ = next(walker)
        for release in releases:
            yield os.path.join(sitepath, release)


def find_base_path_in_config():
    try:
        with open("/etc/apt/mirror.list", "rt") as f:
            for line in f.readlines():
                m = re.match(r"set\s+base_path\s+([\w/-]+)", line)
                if m is None:
                    continue
                return m.group(1)
    except FileNotFoundError:
        pass


def get_sites_dir(base_dir):
    if base_dir is None:
        base_dir = find_base_path_in_config()
        if base_dir is None:
            base_dir = os.getcwd()

    sites_dir = os.path.join(base_dir, "mirror")  # NOTE: fixed as mirror
    if not os.path.isdir(sites_dir):
        raise click.BadOptionUsage("--base-dir", "please specify correct base_path the same as /etc/apt/mirror.list")

    return sites_dir


@click.command("Checking for corrupted files in apt-mirror files")
@click.option("-b", "--base-dir", type=click.Path(exists=True, file_okay=False, readable=True, resolve_path=True),
              help="apt-mirror base_path")
@click.option("--delete/--no-delete", default=False, help="delete corrupted files")
def cli(base_dir, delete):
    sites_dir = get_sites_dir(base_dir)

    has_bad = False
    for mirror in all_mirrors(sites_dir):
        for bad_file in bad_files_in_mirror(mirror):
            has_bad = True

            if delete:
                os.unlink(bad_file)
                prefix = "[DELETED] "
            else:
                prefix = "[ERROR] "
            click.secho(prefix + bad_file, color="red")

    if not has_bad:
        click.echo("No error found!")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    cli()
