# coding: utf-8

import click
import os
import hashlib
import re


class Md5Attr(object):
    def __init__(self, sum, size):
        self.sum = sum
        self.size = size


def dist_md5attrs(dist_dir):
    """ Parse md5 attributes in Release file """
    md5attrs = {}

    with open(os.path.join(dist_dir, "Release"), "rt") as f:
        list_start = False

        for line in f.readlines():
            if list_start:
                if not line.startswith(" "):
                    return md5attrs
                sum, size, rname = line.split()
                md5attrs[os.path.join(dist_dir, rname)] = Md5Attr(
                    sum, int(size))

            elif line.startswith("MD5Sum:"):
                list_start = True


def pkg_attrs(pkg_desc_path):
    with open(pkg_desc_path, "rt") as f:
        attrs = {}
        last_key = None
        for line in f.readlines():
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


def pool_md5attrs(dist_dir, pool_dir):
    """ Parse md5 attributes in Packages file"""
    md5attrs = {}
    pool_parent_dir = os.path.dirname(pool_dir)

    for root, _, files in os.walk(dist_dir):
        for filename in files:
            if filename != "Packages":
                continue
            for pkgattr in pkg_attrs(os.path.join(root, filename)):
                if pkgattr["Filename"].startswith("pool/"):
                    md5attrs[os.path.join(pool_parent_dir, pkgattr["Filename"])] = Md5Attr(
                        pkgattr["MD5sum"], int(pkgattr["Size"]))

    return md5attrs


def is_md5_correct(filepath, md5attr):
    s = os.stat(filepath)
    if md5attr.size != s.st_size:
        return False

    with open(filepath, "rb") as f:
        m = hashlib.md5()
        while True:
            data = f.read(1024 * 1024)
            if not data:
                break

            m.update(data)
        sum = m.hexdigest()
        if sum != md5attr.sum:
            return False

    return True


def bad_files_in_dir(dirpath, md5attrs):
    for root, _, files in os.walk(dirpath):
        for filename in files:
            filepath = os.path.join(root, filename)
            if filepath in md5attrs:
                if not is_md5_correct(filepath, md5attrs[filepath]):
                    yield filepath


def bad_files_in_mirror(mirror_dir):
    dist_root = os.path.join(mirror_dir, "dists")
    walker = os.walk(dist_root)
    _, subdirs, _ = next(walker)

    dist_dirs = [os.path.join(dist_root, subdir)
                 for subdir in subdirs]
    pool_dir = os.path.join(mirror_dir, "pool")

    for dist_dir in dist_dirs:
        click.echo("checking %s ..." % dist_dir)
        yield from bad_files_in_dir(dist_dir, dist_md5attrs(dist_dir))
        yield from bad_files_in_dir(pool_dir, pool_md5attrs(dist_dir, pool_dir))


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
        raise click.BadOptionUsage("--base-dir")

    return sites_dir


@click.command("Checking for corrupted files in apt-mirror files")
@click.option("-b", "--base-dir", type=click.Path(exists=True, file_okay=False, readable=True, resolve_path=True), help="apt-mirror base_path")
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


if __name__ == "__main__":
    cli()
