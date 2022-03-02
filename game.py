class Game():

    def __init__(self):
        self._cards = ["loup", "villageois", "cupidon",
                       "voyante", "petite-fille", "sorciere"]

        # List of members of the party (Discord.Member objects)
        self._members = []
        self._n_members = 0

        self._couple = []

        # For the <sorciere> (witch) role
        self._current_victim = None
        self._heal_potion = 1
        self._poison_potion = 1
        self._daily_victims = [] # List of all the victims that will be killed in the night (Discord.Member objects)

        # Dict attributing a role to each member(object), example: {Discord.Member:"loup"}
        self._roles = {}

    @property
    def members(self):
        return self._members

    @members.setter
    def members(self, m):
        self._members = m

    @property
    def couple(self):
        return self._couple

    @couple.setter
    def couple(self, l):
        self._couple = l

    @property
    def n_members(self):
        return self._n_members

    @n_members.setter
    def n_members(self, n):
        self._n_members = n

    @property
    def cards(self):
        return self._cards

    @property
    def roles(self):
        return self._roles

    @roles.setter
    def roles(self, d):
        self._roles = d

    @property
    def current_victim(self):
        return self._current_victim

    @current_victim.setter
    def current_victim(self, member):
        self._current_victim = member

    def good_config(self, dic):
        return True

    def remove_member(self, member):
        self._n_members -= 1
        self._roles.pop(member)
        self._members.remove(member)

    @property
    def daily_victims(self):
        return self._daily_victims

    def add_member_to_victims(self, member):
        self._daily_victims.append(member)

    def clean_daily_victims(self):
        self._daily_victims = []

    @property
    def heal_potion(self):
        return self._heal_potion

    @property
    def poison_potion(self):
        return self._poison_potion

    def remove_poison(self):
        self._poison_potion = 0

    def remove_heal(self):
        self._heal_potion = 0

    def finished(self):
        if "loup" in self.roles.values():
            for role in self.roles.values():
                if role != "loup":
                    return False
            return True
        return True
