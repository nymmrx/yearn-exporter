from dataclasses import dataclass
from typing import List

from brownie.network.contract import Contract, InterfaceContainer

from yearn import strategies, uniswap
from yearn.events import fetch_events
from yearn.mutlicall import fetch_multicall

VAULT_VIEWS_SCALED = [
    "totalAssets",
    "maxAvailableShares",
    "pricePerShare",
    "debtOutstanding",
    "creditAvailable",
    "expectedReturn",
    "totalSupply",
    "availableDepositLimit",
    "depositLimit",
    "totalDebt",
    "debtLimit",
]


@dataclass
class VaultV2:
    name: str
    api_version: str
    vault: InterfaceContainer
    strategies: List[strategies.Strategy]

    def __post_init__(self):
        # mutlicall-safe views with 0 inputs and numeric output.
        self._views = [
            x["name"]
            for x in self.vault.abi
            if x["type"] == "function"
            and x["stateMutability"] == "view"
            and not x["inputs"]
            and x["outputs"][0]["type"] == "uint256"
        ]

    def describe(self):
        scale = 10 ** self.vault.decimals()
        try:
            results = fetch_multicall(*[[self.vault, view] for view in self._views])
            info = dict(zip(self._views, results))
            for name in info:
                if name in VAULT_VIEWS_SCALED:
                    info[name] /= scale
            info["strategies"] = {}
        except ValueError as e:
            info = {"strategies": {}}
        for strat in self.strategies:
            info["strategies"][strat.name] = strat.describe()

        info["token price"] = uniswap.token_price(self.vault.token())
        if "totalAssets" in info:
            info["tvl"] = info["token price"] * info["totalAssets"]

        return info


def get_vaults(event_key="NewVault"):
    registry = Contract("v2.registry.ychad.eth")
    events = fetch_events(registry)
    versions = {x["api_version"]: Contract(x["template"]).abi for x in events["NewRelease"]}
    vaults = [
        Contract.from_abi(f'Vault v{vault["api_version"]}', vault["vault"], versions[vault["api_version"]])
        for vault in events[event_key]
    ]
    symbols = fetch_multicall(*[[x, "symbol"] for x in vaults])
    names = [f'{name} {vault["api_version"]}' for vault, name in zip(events[event_key], symbols)]
    return [
        VaultV2(name=name, api_version=event["api_version"], vault=vault, strategies=[])
        for name, vault, event in zip(names, vaults, events[event_key])
    ]


def get_experimental_vaults():
    return get_vaults("NewExperimentalVault")

