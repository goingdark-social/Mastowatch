from typing import TYPE_CHECKING, Any, TypeVar, Union

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.put_push_subscription_body_data_alerts import \
        PutPushSubscriptionBodyDataAlerts


T = TypeVar("T", bound="PutPushSubscriptionBodyData")


@_attrs_define
class PutPushSubscriptionBodyData:
    """Object containing properties

    Attributes:
        alerts (Union[Unset, PutPushSubscriptionBodyDataAlerts]):
    """

    alerts: Union[Unset, "PutPushSubscriptionBodyDataAlerts"] = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        alerts: Union[Unset, dict[str, Any]] = UNSET
        if not isinstance(self.alerts, Unset):
            alerts = self.alerts.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update({})
        if alerts is not UNSET:
            field_dict["alerts"] = alerts

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: dict[str, Any]) -> T:
        from ..models.put_push_subscription_body_data_alerts import \
            PutPushSubscriptionBodyDataAlerts

        d = src_dict.copy()
        _alerts = d.pop("alerts", UNSET)
        alerts: Union[Unset, PutPushSubscriptionBodyDataAlerts]
        if isinstance(_alerts, Unset):
            alerts = UNSET
        else:
            alerts = PutPushSubscriptionBodyDataAlerts.from_dict(_alerts)

        put_push_subscription_body_data = cls(
            alerts=alerts,
        )

        put_push_subscription_body_data.additional_properties = d
        return put_push_subscription_body_data

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
