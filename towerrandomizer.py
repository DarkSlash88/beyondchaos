from copy import deepcopy, copy
from utils import (TOWER_CHECKPOINTS_TABLE, TOWER_LOCATIONS_TABLE,
                   utilrandom as random)
from locationrandomizer import get_locations, get_unused_locations, Entrance
from itertools import product

SIMPLE, OPTIONAL, DIRECTIONAL = 's', 'o', 'd'
MAX_NEW_EXITS = 25  # maybe?
MAX_NEW_EXITS = 42  # prob. not
MAX_NEW_MAPS = 26  # 6 more for fanatics tower

locdict = {}
# dealing with one-ways: when identifying the "from" entrance in a route,
# retroactively add the "to" entrance to earlier in the route?
towerlocids = [int(line.strip(), 0x10) for line in open(TOWER_LOCATIONS_TABLE)]
map_bans = [353, 143, 319, 179]


class SpecialInstructions:
    def __init__(self):
        self.deadends = set([])
        self.oneways = set([])
        self.nochanges = set([])
        self.removes = set([])

    @property
    def invalid(self):
        return self.nochanges | self.removes

    def add_item(self, item, attribute):
        a, b = item
        item = int(a), int(b)
        getattr(self, attribute).add(item)

    def add_nochange(self, item):
        self.add_item(item, 'nochanges')

    def add_remove(self, item):
        self.add_item(item, 'removes')

    def add_oneway(self, item):
        fro, to = item
        fro = tuple(map(int, fro))
        to = tuple(map(int, to))
        self.oneways.add((fro, to))

    def add_deadend(self, item):
        self.add_item(item, 'deadends')

    def remove_removes(self):
        for mapid, entid in self.removes:
            location = locdict[mapid]
            ents = [e for e in location.entrances if e.entid == entid]
            for ent in ents:
                location.entrance_set.entrances.remove(ent)


si = SpecialInstructions()
locexchange = {}


def connect_segments(sega, segb):
    exits = {}
    for seg in [sega, segb]:
        if seg.addable or seg.ruletype == OPTIONAL:
            entrances = seg.sorted_entrances
            random.shuffle(entrances)
        elif seg.ruletype == DIRECTIONAL:
            entrances = seg.entrances.values()[0]

        for e in entrances:
            shortsig = e.shortsig
            if shortsig not in seg.links:
                exits[seg] = e
                break
        else:
            raise Exception("No exits available.")

    sega.links[exits[sega].shortsig] = exits[segb].signature
    segb.links[exits[segb].shortsig] = exits[sega].signature


def clear_entrances(location):
    nochanges = [b for (a, b) in si.nochanges if a == location.locid]
    location.entrance_set.entrances = [e for e in location.entrances if
                                       e.entid in nochanges]


def clear_unused_locations():
    unused_locations = get_unused_locations()
    for u in unused_locations:
        clear_entrances(u)


def get_appropriate_location(loc):
    unused_locations = get_unused_locations()
    if loc in locexchange:
        return locexchange[loc]
    elif loc.locid in towerlocids:
        clear_entrances(loc)
        locexchange[loc] = loc
        return loc
    else:
        for u in unused_locations:
            if u not in locexchange.values():
                u.copy(loc)
                u.make_tower_flair()
                clear_entrances(u)
                try:
                    assert not u.entrances
                except:
                    import pdb; pdb.set_trace()
                locexchange[loc] = u
                return u
    raise Exception("No appropriate location available.")


def get_inappropriate_location(location):
    reverselocex = dict([(b, a) for (a, b) in locexchange.items()])
    if location in reverselocex:
        return reverselocex[location]
    else:
        return location


class CheckRoomSet:
    def __init__(self):
        self.entrances = {}
        self.links = {}
        self.addable = True
        self.ruletype = None

    def __repr__(self):
        return str(self.entrances)

    def backup(self):
        self.backup_entrances = copy(self.entrances)

    def load_backup(self):
        self.entrances = copy(self.backup_entrances)

    def establish_entrances(self):
        for mapid in self.entrances:
            for e in self.entrances[mapid]:
                loc = get_appropriate_location(e.location)
                sig = e.signature
                _, x, y, _, _, _ = sig
                if e.shortsig not in self.links:
                    #print "WARNING: %s not in links." % str(sig)
                    continue
                sig2 = self.links[e.shortsig]
                loc2id, destx, desty, _, _, _ = sig2
                temploc = locdict[loc2id]
                loc2 = get_appropriate_location(temploc)

                # getting correct x/y values for destination
                tempent = temploc.get_nearest_entrance(destx, desty)
                assert abs(tempent.x - destx) + abs(tempent.y - desty) <= 4
                mirror = tempent.mirror
                dest = 0
                if mirror:
                    destx, desty = mirror.destx, mirror.desty
                    dest = mirror.dest & 0xFE00
                if ((mirror is None or
                        mirror.mirror.location.locid != tempent.location.locid) or
                        abs(tempent.x - destx) + abs(tempent.y - desty) > 4):
                    destx, desty = tempent.x, tempent.y
                assert abs(tempent.x - destx) + abs(tempent.y - desty) <= 4

                entrance = Entrance(None)
                entrance.set_location(loc.locid)
                entrance.x = x
                entrance.y = y
                entrance.destx = destx
                entrance.desty = desty
                entrance.dest = loc2.locid | dest
                effectsigs = [e3.effectsig for e3 in loc.entrances]
                if entrance.effectsig in effectsigs:
                    continue
                loc.entrance_set.entrances.append(entrance)
                loc.validate_entrances()

    @property
    def reachability_factor(self):
        num_entrances = sum([len(self.entrances[k]) for k in self.entrances.keys()])
        num_maps = len(self.entrances.keys())
        if num_entrances - self.numexits < 0:
            return 1000000
        return float(len(num_maps)) / num_entrances

    @property
    def maps(self):
        return self.entrances.keys()

    @property
    def sorted_entrances(self):
        entrances = []
        for es in self.entrances.values():
            entrances.extend(es)
        entrances = sorted(set(entrances),
                           key=lambda e: (e.location.locid, e.entid))
        return entrances

    def generate_reachability_matrix(self):
        from utils import get_matrix_reachability
        entrances = self.sorted_entrances
        edict = dict(zip(entrances, range(len(entrances))))
        basematrix = [0]*len(entrances)
        basematrix = [list(basematrix) for _ in xrange(len(entrances))]
        for e in entrances:
            a = edict[e]
            basematrix[a][a] = 1
            for e2 in self.entrances[e.location.locid]:
                if e2 in edict:
                    b = edict[e2]
                    basematrix[a][b] = 1
                    basematrix[b][a] = 1

        zeroes = sum([row.count(0) for row in basematrix])
        if zeroes == 0:
            if len(basematrix) < self.numexits:
                return None
            self.reachability = basematrix
            return basematrix

        locids = self.entrances.keys()
        for _ in xrange(1000):
            matrix = deepcopy(basematrix)
            candidates = list(entrances)
            random.shuffle(locids)
            done = []
            links = {}
            try:
                for l in locids:
                    if l in done:
                        continue
                    front = [c for c in candidates if c.location.locid == l]
                    back = [c for c in candidates if c not in front]
                    c1 = random.choice(front)
                    c2 = random.choice(back)
                    done.extend([l, c2.location.locid])
                    candidates.remove(c1)
                    candidates.remove(c2)
                    a, b = edict[c1], edict[c2]
                    matrix[a][b] = 1
                    matrix[b][a] = 1
                    links[c1.shortsig] = c2.signature
                    links[c2.shortsig] = c1.signature
            except IndexError:
                continue

            if len(candidates) < self.numexits:
                continue

            prevones = 0
            reach = deepcopy(matrix)
            for _ in xrange(len(entrances)*2):
                reach = get_matrix_reachability(reach)
                zeroes = sum([row.count(0) for row in reach])
                ones = sum([row.count(1) for row in reach])
                assert zeroes + ones == len(entrances)**2
                if ones == prevones:
                    break

            if zeroes == 0:
                break
        else:
            return None

        self.reachability = matrix
        self.links = links
        return matrix

    def add_rule(self, ruletype, mapid, parameters):
        assert type(parameters) in [list, tuple]
        if self.ruletype in [OPTIONAL, DIRECTIONAL]:
            raise Exception("Already set a rule.")

        self.ruletype = ruletype
        if ruletype == SIMPLE:
            # can add simple rooms arbitrarily
            self.addable = True
        elif ruletype in [OPTIONAL, DIRECTIONAL]:
            assert not self.entrances
            if ruletype == OPTIONAL:
                random.shuffle(parameters)
            else:
                assert len(parameters) == 2
            self.addable = False
        for p in parameters:
            self.add_entrance(mapid, p)

    def add_entrance(self, mapid, entid):
        # adding unreachable entrance = asserting it is reachable
        if mapid not in self.entrances:
            self.entrances[mapid] = []
        try:
            entrance = [e for e in locdict[mapid].entrances if e.entid == entid][0]
        except IndexError:
            import pdb; pdb.set_trace()
        if entrance not in self.entrances[mapid]:
            self.entrances[mapid].append(entrance)
        for e in entrance.reachable_entrances:
            if (mapid, e.entid) in si.invalid:
                continue
            if e not in self.entrances[mapid]:
                self.entrances[mapid].append(e)

    def remove_entrance(self, mapid, entid):
        if mapid not in self.entrances:
            return
        entrances = self.entrances[mapid]
        for e in entrances:
            if e.entid == entid:
                self.entrances[mapid].remove(e)


class RouteRouter:
    def __init__(self, starting):
        self.set_starting(starting)
        self.checkpoints = []

    def backup(self):
        for route in self.routes.values():
            for segment in route:
                segment.backup()

    def load_backup(self):
        for route in self.routes.values():
            for segment in route:
                segment.load_backup()

    @property
    def entrances(self):
        entrances = set([])
        for route in self.routes.values():
            for segment in route:
                for zone in segment.entrances.values():
                    entrances |= set(zone)
        return entrances

    def get_unfilled_segment(self):
        routes = list(self.routes.values())
        random.shuffle(routes)
        for route in routes:
            candidates = filter(lambda c: c.addable and not c.entrances, route)
            if candidates:
                if random.randint(1, 5) != 5:
                    segment = min(candidates, key=lambda c: c.reachability_factor)
                else:
                    segment = random.choice(candidates)
                return segment

    def set_starting(self, starting):
        self.starting = []
        for a, b in starting:
            self.starting.append((SIMPLE, int(a), [int(b)]))

    def set_ending(self, ending):
        self.ending = []
        for a, b in ending:
            self.ending.append((SIMPLE, int(a), [int(b)]))

    def add_checkpoint(self, simple, optional, directional):
        assert len(simple + optional + directional) <= 3
        rule = []
        for a, b in simple:
            a, b = int(a), int(b)
            rule.append((SIMPLE, a, [b]))
        for a, options in optional:
            a, options = int(a), map(int, options)
            rule.append((OPTIONAL, a, options))
        for a, fro, to in directional:
            a, fro, to = int(a), int(fro), int(to)
            rule.append((DIRECTIONAL, a, (fro, to)))
        for subrule in rule:
            assert type(subrule[2]) in [list, tuple]
        self.checkpoints.append(rule)

    def construct_check_routes(self):
        random.shuffle(self.checkpoints)
        routes = dict([(i, []) for i in range(3)])

        for rule in [self.starting] + self.checkpoints + [self.ending]:
            parties = range(3)
            random.shuffle(parties)
            assert len(parties) >= len(rule)
            for party, subrule in zip(parties, rule):
                ruletype, mapid, parameters = subrule
                crs = CheckRoomSet()
                crs.add_rule(ruletype, mapid, parameters)
                for p in parameters:
                    for (a, b), (c, d) in si.oneways:
                        if mapid == a and p == b:
                            candidates = filter(lambda crs: crs.addable, routes[party])
                            precrs = random.choice(candidates)
                            precrs.add_rule(SIMPLE, c, [d])
                if (routes[party] and not routes[party][-1].addable and
                        not crs.addable):
                    crs2 = CheckRoomSet()
                    routes[party].append(crs2)
                    crs2.numexits = 2

                if rule in [self.starting, self.ending]:
                    crs.numexits = 1
                else:
                    crs.numexits = 2

                routes[party].append(crs)

        for route in routes.values():
            for crs in route:
                for (mapid, entid) in si.removes | si.nochanges:
                    continue
                    crs.remove_entrance(mapid, entid)

        self.routes = routes


def parse_checkpoints():
    rr = None
    rrs = []
    for line in open(TOWER_CHECKPOINTS_TABLE):
        line = line.strip()
        if line[0] in '#&%-' or '>>' in line:
            continue
        elif line[0] == '!':
            # set new dungeon matrix with given positions
            line = line[1:]
            mappoints = line.split(',')
            mappoints = [tuple(m.split(':')) for m in mappoints]
            rr = RouteRouter(mappoints)
            rrs.append(rr)
        elif line[0] == '$':
            line = line[1:]
            mappoints = line.split(',')
            mappoints = [tuple(m.split(':')) for m in mappoints]
            rr.set_ending(mappoints)
            rr = None
        else:
            items = line.split(',')
            directional = []
            optional = []
            simple = []
            for item in items:
                loc, entrances = tuple(item.split(':'))
                if '>' in entrances:
                    # entrances that must be used, and in a specific order
                    fro, to = tuple(entrances.split('>'))
                    directional.append((loc, fro, to))
                elif '|' in entrances:
                    # entrances that must be used, in no specific order
                    options = entrances.split('|')
                    optional.append((loc, options))
                else:
                    # one entrance
                    simple.append((loc, entrances))
            rr.add_checkpoint(simple, optional, directional)

    for line in open(TOWER_CHECKPOINTS_TABLE):
        line = line.strip()
        if line[0] in '#!$':
            continue
        elif line[0] == '&':
            # these entrances and exits must not be changed
            line = line[1:]
            loc, entrances = tuple(line.split(':'))
            entrances = tuple(entrances.split(','))
            for e in entrances:
                si.add_nochange((loc, e))
        elif line[0] == '-':
            # useless entrances to delete
            line = line[1:]
            loc, entrances = tuple(line.split(':'))
            entrances = tuple(entrances.split(','))
            for e in entrances:
                si.add_remove((loc, e))
        elif line[0] == '%':
            # these should lead nowhere, or backwards
            line = line[1:]
            for rr in rrs:
                si.add_deadend(tuple(line.split(':')))
        elif '>>' in line:
            # one way paths
            fro, to = tuple(line.split('>>'))
            fro = tuple(fro.split(':'))
            to = tuple(to.split(':'))
            si.add_oneway((fro, to))

    return rrs


def assign_maps(rrs, maps=None, new_entrances=None):
    if maps is None:
        maps = towerlocids

    location_entrances = []
    for m in maps:
        location = locdict[m]
        location_entrances.append(location.entrances)

    if new_entrances:
        for e in new_entrances:
            location_entrances.append(e.reachable_entrances)

    for base_entrances in reversed(location_entrances):
        assert len(set([e.location.locid for e in base_entrances])) == 1
        while True:
            entrances = copy(base_entrances)

            def validate(e):
                if e.location is None:
                    return False

                invalid = si.nochanges | si.removes
                if (e.location.locid, e.entid) in invalid:
                    return False

                return True

            entrances = [e for e in entrances if validate(e)]
            used_entrances = [en for rr in rrs for en in rr.entrances]
            entrances = set(entrances) - set(used_entrances)
            if not entrances:
                break

            random.shuffle(rrs)
            for rr in rrs:
                segment = rr.get_unfilled_segment()
                if segment is not None:
                    break

            entrances = sorted(entrances,
                               key=lambda e: (e.location.locid, e.entid))
            if segment is None:
                while True:
                    rr = random.choice(rrs)
                    route = random.choice(rr.routes)

                    def validate(c):
                        if not c.addable:
                            return False
                        locid = entrances[0].location.locid
                        if locid in c.entrances:
                            return False
                        return True

                    candidates = filter(validate, route)
                    if not candidates:
                        continue
                    else:
                        segment = random.choice(candidates)
                        break

            e = random.choice(entrances)
            segment.add_entrance(e.location.locid, e.entid)


def get_new_entrances(filename):
    unused_locations = get_unused_locations(filename)
    candidates = [e for l in get_locations() for e in l.entrances]

    def validate(e):
        # TODO: remove maps with adjacent entrances
        if e.location.locid <= 2:
            return False
        if e.location.locid in towerlocids:
            return False
        if e.location.locid in unused_locations:
            return False
        if e.location.locid in map_bans:
            return False
        reachable = e.reachable_entrances
        if len(reachable) < 2 + random.randint(0, 1):
            return False
        for e2, e3 in product(reachable, reachable):
            value = abs(e2.x - e3.x) + abs(e2.y - e3.y)
            if value == 1:
                return False
        return True

    random.shuffle(candidates)
    used_locations = []
    chosen = []
    num_entrances = 0
    for c in candidates:
        if not validate(c):
            continue
        if c.location.locid in used_locations:
            continue
        num_entrances += len(c.reachable_entrances)
        if num_entrances >= MAX_NEW_EXITS:
            continue
        chosen.append(c)
        used_locations.append(c.location.locid)
        if len(chosen) == MAX_NEW_MAPS:
            break

    return chosen


def randomize_tower(filename):
    for l in get_locations(filename=filename):
        locdict[l.locid] = l

    def make_matrices():
        assert len(rrs) == 2
        for rr in rrs:
            assert len(rr.routes) == 3
            for route in rr.routes.values():
                for segment in route:
                    if segment.addable:
                        m = segment.generate_reachability_matrix()
                        if m is None:
                            return False
        return True

    print "Selecting maps, please wait."
    new_entrances = get_new_entrances(filename=filename)
    print ("Assigning maps, please wait. Because this is random, "
           "it could take a few minutes.")
    counter = 0

    while True:
        clear_unused_locations()
        rrs = parse_checkpoints()
        si.remove_removes()
        for rr in rrs:
            rr.construct_check_routes()

        new_entrances = get_new_entrances(filename=filename)
        assign_maps(rrs, new_entrances=new_entrances)
        done = make_matrices()
        if done:
            break
        counter += 1
        if not counter % 10:
            print random.choice(["Engaging", "Calibrating", "Still Calibrating"])

    usedlinks = set([])
    for rr in rrs:
        for route in rr.routes.values():
            for sega, segb in zip(route, route[1:]):
                connect_segments(sega, segb)

            for segment in route:
                print segment
                links = set(segment.links)
                if usedlinks & links:
                    import pdb; pdb.set_trace()
                    raise Exception("Duplicate entrance detected.")
                usedlinks |= links
                segment.establish_entrances()
            print


if __name__ == "__main__":
    randomize_tower(filename="program.rom")