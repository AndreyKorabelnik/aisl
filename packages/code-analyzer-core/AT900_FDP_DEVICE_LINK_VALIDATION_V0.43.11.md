# AT900 FDP DEVICE_LINK vertical validation

The production source probe resolved a confirmed storage-to-access path:

`ClientProfileDaoImpl.getDevicesByPhones`
`DEVICE_LINK[DEVICE_ID, PHONE_NUMBER, CLIENT_ID, UCP_ID]`
`-> DeviceLinkRecord`
`-> ClientDevicePair`
`-> ClientProfileServiceImpl.findDevicesByPhones`
`-> ServerController.findDevicesByPhones`
`-> POST /deviceIdList`

Confirmed response mappings:

- `DEVICE_LINK.CLIENT_ID -> DevicesByPhonesResponse.phoneToDevice.clientId`
- `DEVICE_LINK.DEVICE_ID -> DevicesByPhonesResponse.phoneToDevice.deviceId`
- `DEVICE_LINK.UCP_ID -> DevicesByPhonesResponse.phoneToDevice.ucpId`

The branch that returns notification-channel data is separate; this evidence confirms that the DEVICE_LINK-backed path exists, not that every runtime request takes it.
