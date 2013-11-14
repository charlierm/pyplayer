import subprocess
import atexit
import os
import functools
import time
import select
import sys

try:
    import queue
except ImportError:
    import Queue as queue



class MPlayerCasting(object):
    types = {
        "Flag": bool,
        "Integer": int,
        "Position": int,
        "Float": float,
        "Time": float,
        "String": str,
        "String list": dict
    }

    @classmethod
    def get_cast(cls, mplayer_type):
        if mplayer_type in cls.types:
            return cls.types[mplayer_type]
        else:
            raise Exception("{0] is not a valid mplayer data type".format(mplayer_type))


class Player(object):

    _base_args = ['-slave', '-idle', '-quiet']


    ignored_props = ["pause"]
    renamed_props = {"pause": "paused"}
    read_only_props = ['length', 'pause', 'stream_end', 'stream_length',
            'stream_start', 'stream_time_pos']


    def __init__(self, exec_path='./mplayer'):
        self.properties = []
        self.exec_path = exec_path
        self._base_args.insert(0, exec_path)
        self._generate_properties()


        self._process = subprocess.Popen(self._base_args,
                                         stdin=subprocess.PIPE, stdout=subprocess.PIPE)

        #Make subprocess quit with python
        atexit.register(self.quit)

        self._process.stdout.flush()

    def _get_getter(self, name, type):
        return


    def _generate_properties(self):
        cmd = [self.exec_path, "-list-properties"]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)

        for line in proc.stdout:
            line = line.split()
            if not line or not line[0].islower():
                continue

            alias = line[0].strip()
            pname = line[0].strip()
            ptype = line[1].strip()
            pmin = line[2].strip()
            pmax = line[3].strip()

            #Check the property shouldn't be ignored
            if pname in self.ignored_props:
                continue

            #Check if the property should be renamed
            if pname in self.renamed_props:
                alias = self.renamed_props[pname]

            #Check the name isn't already in use
            if hasattr(self, alias):
                continue

            if pmin == 'No':
                pmin = None
            else:
                pmin = MPlayerCasting.get_cast(ptype)(pmin)

            if pmax == 'No':
                pmax = None
            else:
                pmax = MPlayerCasting.get_cast(ptype)(pmax)

            #Check if the property should be readonly
            if (pmin is None and pmax is None and pname != 'sub_delay') or (pname in self.read_only_props):
                self._add_property(pname, ptype, pmin, pmax, read_only=True, alias=alias)
            else:
                self._add_property(pname, ptype, pmin, pmax)

            #Add to the properties list
            self.properties.append(alias)



    def _add_property(self, pname, ptype, pmin, pmax, read_only=False, alias=None):
        getter = lambda self: self._get_property(pname, ptype)

        setter = None

        if not alias: alias = pname

        if not read_only:
            setter = lambda self, value: self._set_property(value, pname, ptype, pmin, pmax)

        setattr(self.__class__, alias, property(getter, setter))

    def _run_command(self, command, wait=True):

        #TODO: Currently timeout is not implemented, this means that if for some reason the command fails,
        # the loop will not break.

        is_loadfile = command.startswith("loadfile")

        self._process.stdin.write(command + "\n")

        if not wait:
            return

        while self._process.poll() is None:
            output = self._process.stdout.readline()
            output = output.strip()

            if is_loadfile and output.startswith("Starting playback"):
                return True

            if output.startswith("ANS"):
                result = output.partition('=')[2].strip('\'"')
                if result == "PROPERTY_UNAVAILABLE":
                    return None
                else:
                    return result


    def _get_property(self, prop_name, prop_type):
        cmd = "get_property {0}".format(prop_name)
        result = self._run_command(cmd)
        cast = MPlayerCasting.get_cast(prop_type)

        if cast == bool:
            if result == "no":
                return False
            else:
                return True

        if not result:
            return result
        else:
            return cast(result)


    def _set_property(self, value, pname, ptype, pmin, pmax):

        if pmin is not None and value < pmin:
                raise ValueError('value must be at least {0}'.format(pmin))

        if pmax is not None and value > pmax:
                raise ValueError('value must be at most {0}'.format(pmax))

        cmd = "set_property {0} {1}".format(pname, value)
        self._run_command(cmd, wait=False)



    @property
    def paused(self):
        return self._get_property("pause", "Flag")

    @paused.setter
    def paused(self, value):
        if value is True and not self.paused:
            self.pause()
        else:
            self.resume()

    def resume(self):
        if self.paused:
            self._run_command("pause", wait=False)

    def pause(self):
        if not self.paused:
            self._run_command("pause", wait=False)


    def quit(self):
        self._process.kill()


    def loadfile(self, path):
        if not os.path.isfile(path):
            raise Exception("Not a valid file path")
        self._run_command('loadfile "{0}"\n'.format(path))


    def stop(self):
        self._run_command('stop', wait=False)
