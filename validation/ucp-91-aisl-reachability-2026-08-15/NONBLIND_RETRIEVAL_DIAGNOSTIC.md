# Non-blind deterministic retrieval diagnostic

> Acceptance diagnostic only. The query plan was prepared in a session where Manual Gold had already been inspected. The runtime did not read Gold, but these results MUST NOT be reported as a blind external-agent score.

## 1. Единый ID клиента (ЕПК/CRM-ключ)
- 990 term='ucpId' scope=projected :: com.sbt.bm.ucp.galo.common.GaloRelatedClient :: field=ucpId :: field_name_exact :: doc=None :: inbound=True
- 990 term='ucpId' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=ucpId :: field_name_exact :: doc='Идентификатор соответствующего профиля клиента' :: inbound=False
- 990 term='ucpId' scope=projected :: ru.sbrf.ucp.synapse.gateway.sdoprofile.sdo.model.person.UcpIdSdo :: field=ucpId :: field_name_exact :: doc=None :: inbound=True
- 990 term='ucpId' scope=all_declared_types :: com.sbt.bm.ucp.galo.common.GaloRelatedClient.Builder :: field=ucpId :: field_name_exact :: doc=None :: inbound=False
- 990 term='ucpId' scope=all_declared_types :: com.sbt.bm.ucp.galo.valuation.GaloValuationRelatedSmartProfileObject :: field=ucpId :: field_name_exact :: doc=None :: inbound=True
- 990 term='ucpId' scope=all_declared_types :: com.sbt.bm.ucp.galo.valuation.GaloValuationRelatedSmartProfileObject.Builder :: field=ucpId :: field_name_exact :: doc=None :: inbound=False
- 970 term='идентификатор' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.AccessibilityType :: field=id :: field_documentation_summary_exact :: doc='Идентификатор' :: inbound=True
- 970 term='идентификатор' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.AddressSubType :: field=id :: field_documentation_summary_exact :: doc='Идентификатор' :: inbound=True
- 970 term='идентификатор' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.AgreementObjectiveType :: field=id :: field_documentation_summary_exact :: doc='Идентификатор' :: inbound=False
- 970 term='идентификатор' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.AgreementRelatedReason :: field=id :: field_documentation_summary_exact :: doc='Идентификатор' :: inbound=False

## 2. Маппинг ID по системам
- 1000 term='equivalent' scope=projected :: com.sbt.bm.ucp.common.model.party.equivalent.Equivalent :: field=None :: type_name_exact :: doc='Идентификаторы в других системах' :: inbound=True
- 990 term='externalSystem' scope=projected :: com.sbt.bm.ucp.common.model.party.equivalent.Equivalent :: field=externalSystem :: field_name_exact :: doc='Идентификатор внешней системы' :: inbound=True
- 990 term='externalSystem' scope=projected :: com.sbt.bm.ucp.common.model.party.extension.UndefinedValue :: field=externalSystem :: field_name_exact :: doc='Идентификатор внешней системы' :: inbound=False
- 990 term='externalSystem' scope=projected :: com.sbt.bm.ucp.galo.common.GaloRelatedProduct :: field=externalSystem :: field_name_exact :: doc=None :: inbound=True
- 990 term='externalSystem' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormEquivalent :: field=externalSystem :: field_name_exact :: doc='Идентификатор внешней системы' :: inbound=True
- 990 term='externalSystem' scope=projected :: com.sbt.bm.ucp.smpr.RealEstateEquivalent :: field=externalSystem :: field_name_exact :: doc='Идентификатор внешней системы' :: inbound=True
- 990 term='externalSystem' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.equivalent.Equivalent.Builder :: field=externalSystem :: field_name_exact :: doc=None :: inbound=False
- 990 term='externalSystem' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.extension.UndefinedValue.Builder :: field=externalSystem :: field_name_exact :: doc=None :: inbound=False
- 970 term='идентификаторы в других системах' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=equivalents :: field_documentation_display_name_exact :: doc='Физические лица' :: inbound=True
- 970 term='идентификаторы в других системах' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=equivalents :: field_documentation_display_name_exact :: doc=None :: inbound=False

## 3. ФИО и данные авторизации
- 970 term='ФИО' scope=projected :: com.sbt.bm.ucp.common.model.party.ManagerEmployeeInfo :: field=employeeFullName :: field_documentation_summary_exact :: doc='ФИО' :: inbound=True
- 970 term='ФИО' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=names :: field_documentation_summary_exact :: doc='ФИО' :: inbound=False
- 970 term='ФИО' scope=projected :: com.sbt.bm.ucp.retail.model.individual.IndividualEmployeeInfo :: field=employeeFullName :: field_documentation_summary_exact :: doc='ФИО' :: inbound=True
- 970 term='ФИО' scope=all_declared_types :: com.sbt.bm.ucp.taxprofile.model.PersonTaxProfile :: field=name :: field_documentation_summary_exact :: doc='ФИО' :: inbound=False
- 970 term='имя физического лица' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=names :: field_documentation_display_name_exact :: doc='Список имён ФЛ текущее имя, бывшие имена и на других языках' :: inbound=True
- 960 term='ФИО' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormName :: field=None :: type_documentation_summary_exact :: doc='ФИО' :: inbound=True
- 940 term='identification' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.Inn :: field=identificationFlags :: field_name_prefix :: doc=None :: inbound=False
- 940 term='identification' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.OtherDocument :: field=identificationFlags :: field_name_prefix :: doc=None :: inbound=False
- 940 term='identification' scope=projected :: com.sbt.bm.ucp.common.model.party.IdentificationFlag :: field=identificationFlagType :: field_name_prefix :: doc='Тип флага' :: inbound=True
- 940 term='identification' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=identifications :: field_name_prefix :: doc='Документы' :: inbound=False

## 4. Возраст / дата рождения
- 970 term='дата рождения' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=birthDate :: field_documentation_summary_exact :: doc='Дата рождения' :: inbound=False
- 970 term='дата рождения' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=birthDate :: field_documentation_display_name_exact :: doc='Физические лица' :: inbound=True
- 970 term='дата рождения' scope=all_declared_types :: com.sbt.bm.ucp.taxprofile.model.BirthDateTaxProfile :: field=birthDate :: field_documentation_summary_exact :: doc='Дата рождения' :: inbound=True
- 970 term='дата рождения' scope=all_declared_types :: com.sbt.bm.ucp.taxprofile.model.PersonTaxProfile :: field=birthDate :: field_documentation_summary_exact :: doc='Дата рождения' :: inbound=False
- 970 term='дата рождения' scope=all_declared_types :: com.sbt.ucp.unconfirmed.model.InternalPassportElgoOrderAttributes :: field=birthDate :: field_documentation_summary_exact :: doc='Дата рождения' :: inbound=True
- 960 term='дата рождения' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormBirthDate :: field=None :: type_documentation_summary_exact :: doc='Дата рождения' :: inbound=True
- 960 term='дата рождения' scope=projected :: com.sbt.bm.ucp.retail.model.individual.BirthDate :: field=None :: type_documentation_display_name_exact :: doc=None :: inbound=True
- 940 term='birth' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=birthCountry :: field_name_prefix :: doc=None :: inbound=False
- 940 term='birth' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=birthDate :: field_name_prefix :: doc='Дата рождения' :: inbound=False
- 940 term='birth' scope=projected :: com.sbt.bm.ucp.retail.model.individual.BirthPlace :: field=birthPlace :: field_name_prefix :: doc='Стандартизованное место рождения одной строкой' :: inbound=True

## 5. Пол
- 1000 term='gender' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Gender :: field=None :: type_name_exact :: doc='Пол' :: inbound=True
- 990 term='gender' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=gender :: field_name_exact :: doc='Пол' :: inbound=False
- 990 term='gender' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=gender :: field_name_exact :: doc='Пол' :: inbound=True
- 990 term='gender' scope=projected :: ru.sbrf.ucp.synapse.gateway.sdoprofile.sdo.model.person.GenderSdo :: field=gender :: field_name_exact :: doc=None :: inbound=True
- 990 term='gender' scope=projected :: ru.sbrf.ucp.synapse.gateway.sdoprofile.sdo.model.person.PersonSdo :: field=gender :: field_name_exact :: doc=None :: inbound=False
- 990 term='gender' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=gender :: field_name_exact :: doc=None :: inbound=False
- 990 term='gender' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.Gender.Builder :: field=gender :: field_name_exact :: doc=None :: inbound=False
- 970 term='Пол' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=gender :: field_documentation_summary_exact :: doc='Пол' :: inbound=False
- 970 term='Пол' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=gender :: field_documentation_summary_exact :: doc='Пол' :: inbound=True
- 960 term='Пол' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormGender :: field=None :: type_documentation_summary_exact :: doc='Пол' :: inbound=True

## 6. Регион / город / привязка к ВСП
- 970 term='регион' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.Address :: field=region :: field_documentation_display_name_exact :: doc=None :: inbound=True
- 970 term='регион' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.PhoneNumber :: field=region :: field_documentation_display_name_exact :: doc=None :: inbound=True
- 970 term='регион' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormAddress :: field=region :: field_documentation_summary_exact :: doc='Регион' :: inbound=True
- 970 term='регион' scope=projected :: com.sbt.bm.ucp.smpr.CoreAddress :: field=region :: field_documentation_summary_exact :: doc='Регион' :: inbound=True
- 970 term='регион' scope=all_declared_types :: com.sbt.bm.ucp.retail.mbc.model.MbcRequest :: field=region :: field_documentation_summary_exact :: doc='Регион' :: inbound=False
- 970 term='город' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.Address :: field=city :: field_documentation_display_name_exact :: doc=None :: inbound=True
- 970 term='город' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormAddress :: field=city :: field_documentation_summary_exact :: doc='Город' :: inbound=True
- 970 term='город' scope=projected :: com.sbt.bm.ucp.retail.model.individual.BirthPlace :: field=city :: field_documentation_summary_exact :: doc='Город' :: inbound=True
- 970 term='город' scope=projected :: com.sbt.bm.ucp.smpr.CoreAddress :: field=city :: field_documentation_summary_exact :: doc='Город' :: inbound=True
- 970 term='город' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Travelling :: field=city :: field_documentation_summary_exact :: doc='Город' :: inbound=False

## 7. Роль и правовой статус: ФЛ / ИП / ЮЛ / самозанятый
- 970 term='роли сущности' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=objectRoles :: field_documentation_summary_exact :: doc='Роли сущности' :: inbound=True
- 970 term='роли сущности' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=objectRoles :: field_documentation_summary_exact :: doc='Роли сущности' :: inbound=False
- 940 term='legal' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.LegalClientSubType :: field=legalClientType :: field_name_prefix :: doc='Тип корпоративного клиента' :: inbound=False
- 940 term='legal' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.IndividualLegalCapacityDocument :: field=legalCapacityType :: field_name_prefix :: doc=None :: inbound=False
- 940 term='legal' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=legalRepresentative :: field_name_prefix :: doc='Признак, определяющий, является ли данный клиент законным представителем другого клиента True если является представителем' :: inbound=True
- 940 term='legal' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=legalRepresentative :: field_name_prefix :: doc='Признак, определяющий, является ли данный клиент законным представителем другого клиента True если является представителем' :: inbound=False
- 940 term='legal' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.identification.IndividualLegalCapacityDocument.Builder :: field=legalCapacityType :: field_name_prefix :: doc=None :: inbound=False
- 940 term='role' scope=projected :: com.sbt.bm.ucp.galo.common.GaloClientRole :: field=roleStatus :: field_name_prefix :: doc=None :: inbound=True
- 940 term='role' scope=all_declared_types :: com.sbt.bm.ucp.galo.common.GaloClientRole.Builder :: field=roleStatus :: field_name_prefix :: doc=None :: inbound=False
- 930 term='legal' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.LegalClassification :: field=None :: type_name_prefix :: doc='Справочник кодов ОПФ' :: inbound=False

## 8. Клиентский сегмент банка (масс, массмаркет+, премиум, Первый и т.п.)
- 960 term='сегмент' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.Segment :: field=None :: type_documentation_summary_exact :: doc='Сегмент' :: inbound=False
- 960 term='группы клиентов' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.PartyGroup :: field=None :: type_documentation_summary_exact :: doc='Группы клиентов' :: inbound=True
- 930 term='VIP' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.VipCategory :: field=None :: type_name_prefix :: doc='Категория VIP-клиента' :: inbound=True
- 890 term='сегмент' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.SegmentFz209 :: field=None :: type_documentation_summary_prefix :: doc='Сегмент по 209-ФЗ' :: inbound=False
- 830 term='VIP' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupVipClientCategory :: field=category :: field_documentation_summary_substring :: doc='Категория VIP-клиента' :: inbound=False
- 810 term='VIP' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupVipClientCategory.Builder :: field=category :: field_type_prefix :: doc=None :: inbound=False
- 800 term='VIP' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.ToggleVipControlGroupOperation :: field=None :: type_name_substring :: doc=None :: inbound=False
- 780 term='сегмент' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.OrganizationSizeType :: field=None :: type_documentation_summary_substring :: doc='Справочник сегментов бизнеса' :: inbound=False
- 780 term='сегмент' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.SubSegment :: field=None :: type_documentation_summary_substring :: doc='Подсегмент' :: inbound=False

## 9. Тип занятости / отрасль / доходная группа
- 970 term='сфера деятельности' scope=projected :: com.sbt.bm.ucp.customerjourney.model.EmploymentInfo :: field=activitySphere :: field_documentation_summary_exact :: doc='Сфера деятельности' :: inbound=True
- 970 term='сфера деятельности' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPlaceOfWork :: field=activitySphere :: field_documentation_summary_exact :: doc='Сфера деятельности' :: inbound=True
- 970 term='сфера деятельности' scope=projected :: com.sbt.bm.ucp.retail.model.individual.PlaceOfWork :: field=fieldOfActivity :: field_documentation_summary_exact :: doc='Сфера деятельности' :: inbound=True
- 970 term='место работы' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=placeOfWork :: field_documentation_summary_exact :: doc='Место работы' :: inbound=False
- 970 term='место работы' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=placesOfWork :: field_documentation_summary_exact :: doc='Место работы' :: inbound=True
- 970 term='финансовое положение' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=welfare :: field_documentation_summary_exact :: doc='Финансовое положение' :: inbound=True
- 960 term='сфера деятельности' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.IndividActivSphere :: field=None :: type_documentation_summary_exact :: doc='Сфера деятельности' :: inbound=True
- 960 term='место работы' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPlaceOfWork :: field=None :: type_documentation_summary_exact :: doc='Место работы' :: inbound=True
- 960 term='место работы' scope=projected :: com.sbt.bm.ucp.retail.model.individual.PlaceOfWork :: field=None :: type_documentation_summary_exact :: doc='Место работы' :: inbound=True
- 910 term='занятост' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPlaceOfWork :: field=occupation :: field_documentation_summary_prefix :: doc='Занятость' :: inbound=True

## 10. Состав семьи / дети / семейный статус
- 970 term='семейное положение' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=maritalInfo :: field_documentation_summary_exact :: doc='Семейное положение' :: inbound=False
- 970 term='семейное положение' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMaritalInfo :: field=maritalStatus :: field_documentation_summary_exact :: doc='Семейное положение' :: inbound=True
- 970 term='семейное положение' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=maritalStatus :: field_documentation_summary_exact :: doc='Семейное положение' :: inbound=True
- 960 term='семейное положение' scope=projected :: com.sbt.bm.ucp.retail.model.individual.MaritalStatus :: field=None :: type_documentation_summary_exact :: doc='Семейное положение' :: inbound=True
- 940 term='marital' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=maritalInfo :: field_name_prefix :: doc='Семейное положение' :: inbound=False
- 940 term='marital' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMaritalInfo :: field=maritalStatus :: field_name_prefix :: doc='Семейное положение' :: inbound=True
- 940 term='marital' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=maritalStatus :: field_name_prefix :: doc='Семейное положение' :: inbound=True
- 940 term='marital' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=maritalInfo :: field_name_prefix :: doc=None :: inbound=False
- 940 term='marital' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMaritalInfo.Builder :: field=maritalStatus :: field_name_prefix :: doc=None :: inbound=False
- 930 term='marital' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.MaritalStatusType :: field=None :: type_name_prefix :: doc='Справочник типов семейных положений' :: inbound=True

## 11. Признак сотрудника банка / VIP / связанной стороны
- 930 term='VIP' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.VipCategory :: field=None :: type_name_prefix :: doc='Категория VIP-клиента' :: inbound=True
- 830 term='сотрудника Сбербанка' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=employeeInfos :: field_documentation_summary_substring :: doc='Информация сотрудника Сбербанка' :: inbound=True
- 830 term='VIP' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupVipClientCategory :: field=category :: field_documentation_summary_substring :: doc='Категория VIP-клиента' :: inbound=False
- 830 term='связан' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=associatedIndividualGroupId :: field_documentation_summary_substring :: doc='Идентификатор группы Связанных Физических Лиц' :: inbound=True
- 830 term='связан' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockInfo :: field=partyModRqId :: field_documentation_summary_substring :: doc='Идентификатор связанного запроса на изменение' :: inbound=True
- 810 term='VIP' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupVipClientCategory.Builder :: field=category :: field_type_prefix :: doc=None :: inbound=False
- 800 term='VIP' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.ToggleVipControlGroupOperation :: field=None :: type_name_substring :: doc=None :: inbound=False
- 780 term='сотрудника Сбербанка' scope=projected :: com.sbt.bm.ucp.retail.model.individual.IndividualEmployeeInfo :: field=None :: type_documentation_summary_substring :: doc='Информация сотрудника Сбербанка' :: inbound=True

## 12. Согласия и признаки отказа от коммуникации (opt-in/opt-out по каналам)
- 970 term='согласия клиента' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=clientConsents :: field_documentation_summary_exact :: doc='Согласия клиента' :: inbound=True
- 970 term='согласия клиента' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=clientConsents :: field_documentation_summary_exact :: doc='Согласия клиента' :: inbound=False
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.common.model.party.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 960 term='согласия клиента' scope=projected :: com.sbt.bm.ucp.common.model.party.Consent :: field=None :: type_documentation_summary_exact :: doc='Согласия клиента' :: inbound=True
- 960 term='согласия клиента' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Consent :: field=None :: type_documentation_summary_exact :: doc='Согласия клиента' :: inbound=True
- 910 term='соглас' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=consent :: field_documentation_display_name_prefix :: doc=None :: inbound=False
- 910 term='соглас' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=clientConsents :: field_documentation_summary_prefix :: doc='Согласия клиента' :: inbound=True
- 910 term='соглас' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=clientConsents :: field_documentation_summary_prefix :: doc='Согласия клиента' :: inbound=False
- 910 term='канал' scope=projected :: com.sbt.bm.ucp.common.model.party.InfoFlowChannel :: field=infoFlowChannelType :: field_documentation_summary_prefix :: doc='Канал поступления информации' :: inbound=True

## 13. Языковые и доступностные особенности (язык, слабовидящий, нужен крупный шрифт)
- 970 term='язык' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.Address :: field=language :: field_documentation_summary_exact :: doc='Язык' :: inbound=True
- 970 term='язык' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.Inn :: field=language :: field_documentation_display_name_exact :: doc=None :: inbound=False
- 970 term='язык' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.OtherDocument :: field=language :: field_documentation_display_name_exact :: doc=None :: inbound=False
- 970 term='язык' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.CertificateOnDisability :: field=language :: field_documentation_display_name_exact :: doc=None :: inbound=False
- 970 term='язык' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.DeathCertificate :: field=language :: field_documentation_display_name_exact :: doc=None :: inbound=False
- 970 term='язык' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.identificatation.AbstractIdentification :: field=language :: field_documentation_display_name_exact :: doc=None :: inbound=True
- 910 term='неграмот' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=literacy :: field_documentation_summary_prefix :: doc='Неграмотность' :: inbound=True
- 890 term='неграмот' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Literacy :: field=None :: type_documentation_summary_prefix :: doc='Неграмотнось' :: inbound=True
- 830 term='доступност' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.PhoneNumber :: field=timeAvailabilityFrom :: field_documentation_summary_substring :: doc='Временной интервал доступности с' :: inbound=True
- 830 term='доступност' scope=projected :: com.sbt.bm.ucp.retail.model.individual.CustomerAvailabilityTime :: field=endTimeInMinutes :: field_documentation_summary_substring :: doc='Конец периода доступности в минутах от полуночи' :: inbound=True

## 14. Стаж в банке (дата первого продукта)
- 940 term='service' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.Region :: field=serviceZone :: field_name_prefix :: doc='Зона обслуживания' :: inbound=True
- 940 term='service' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpClientInfChangeRbEpkAsApiLink :: field=serviceCode :: field_name_prefix :: doc='Сервис SberAPI для автоматизированной системы, с которой ЕПК РБ ведет обмен информацией по клиентам' :: inbound=False
- 940 term='service' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPhotoFolder :: field=serviceAccount :: field_name_prefix :: doc='Тех.учетка, используемая для доступа к папке в ЕСМ' :: inbound=True
- 940 term='service' scope=projected :: com.sbt.bm.ucp.retail.model.individual.BirthDate :: field=serviceAttributes :: field_name_prefix :: doc='Служебные атрибуты' :: inbound=True
- 940 term='service' scope=projected :: com.sbt.bm.ucp.retail.model.individual.DeathDate :: field=serviceAttributes :: field_name_prefix :: doc='Служебные атрибуты' :: inbound=True
- 940 term='service' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=serviceData :: field_name_prefix :: doc='Служебная информация для технических нужд' :: inbound=False
- 940 term='service' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPhotoFolder.Builder :: field=serviceAccount :: field_name_prefix :: doc=None :: inbound=False
- 830 term='начало обслуживания' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=serviceStartDate :: field_documentation_summary_substring :: doc='Дата начало обслуживания клиента' :: inbound=True
- 830 term='начало обслуживания' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=serviceStartDate :: field_documentation_summary_substring :: doc='Дата начало обслуживания клиента' :: inbound=False
- 830 term='обслуживания клиента' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=serviceEndDate :: field_documentation_summary_substring :: doc='Дата окончания обслуживания клиента' :: inbound=True

## 15. Основной канал взаимодействия
- 1000 term='channel' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.Channel :: field=None :: type_name_exact :: doc='Канал (для которого получено согласие на рассылку)' :: inbound=True
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.common.model.party.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 940 term='channel' scope=all_declared_types :: com.sbt.bm.storage.model.OmniMemoryFact :: field=channelId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='channel' scope=all_declared_types :: com.sbt.bm.storage.model.OmniMemoryFact.Builder :: field=channelId :: field_name_prefix :: doc=None :: inbound=False
- 910 term='канал' scope=projected :: com.sbt.bm.ucp.common.model.party.InfoFlowChannel :: field=infoFlowChannelType :: field_documentation_summary_prefix :: doc='Канал поступления информации' :: inbound=True
- 910 term='канал' scope=projected :: com.sbt.bm.ucp.common.model.party.UserInfo :: field=infoFlowChannel :: field_documentation_summary_prefix :: doc='Канал поступления информации' :: inbound=True
- 910 term='канал' scope=projected :: com.sbt.bm.ucp.smpr.DeliveryAddressInfoFlowChannel :: field=infoFlowChannelType :: field_documentation_summary_prefix :: doc='Канал поступления информации' :: inbound=True
- 880 term='channel' scope=projected :: com.sbt.bm.ucp.common.model.party.Consent :: field=consentChannels :: field_name_substring :: doc='Канал' :: inbound=True
- 880 term='channel' scope=projected :: com.sbt.bm.ucp.common.model.party.InfoFlowChannel :: field=infoFlowChannelType :: field_name_substring :: doc='Канал поступления информации' :: inbound=True

## 16. Признак цифровой активности (digital-скор)
- 830 term='активност' scope=projected :: com.sbt.bm.ucp.common.model.unsuspect.PartyUnsuspect :: field=active :: field_documentation_summary_substring :: doc='Признак активности' :: inbound=False
- 830 term='активност' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockInfo :: field=deactivated :: field_documentation_summary_substring :: doc='Признак активности блокировки' :: inbound=True
- 830 term='активност' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity :: field=deactivated :: field_documentation_summary_substring :: doc='Признак активности блокировки' :: inbound=False

## 17. Частота визитов в ВСП за 3/6/12 мес
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=trusteeDocumentNumber :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.DeathInfo :: field=sourceChannelRequisites :: field_documentation_summary_substring :: doc='Реквизиты источника данных о смерти' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.DeathCertificate :: field=comment :: field_documentation_summary_substring :: doc='Реквизиты врачебного свидетельства, констатирующего смерть' :: inbound=False

## 18. Дата и цель последнего визита в ВСП
- 910 term='цель' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.PurposeOfInvestment :: field=purposeOfInvestment :: field_documentation_summary_prefix :: doc='Цель инвестирования' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=trusteeDocumentNumber :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.DeathInfo :: field=sourceChannelRequisites :: field_documentation_summary_substring :: doc='Реквизиты источника данных о смерти' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.DeathCertificate :: field=comment :: field_documentation_summary_substring :: doc='Реквизиты врачебного свидетельства, констатирующего смерть' :: inbound=False

## 19. Типичный день недели и время визита
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney :: field=versionStartDate :: field_documentation_summary_prefix :: doc='Время изменения в клиентском модуле' :: inbound=False
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.DistantClientManager :: field=endDate :: field_documentation_summary_prefix :: doc='Время деактивации записи' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.EmploymentInfo :: field=versionStartDate :: field_documentation_summary_prefix :: doc='Время изменения в клиентском модуле' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.PreferredLanguage :: field=updateDateTime :: field_documentation_summary_prefix :: doc='Время изменения в источнике' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=updateDateTime :: field_documentation_summary_prefix :: doc='Время изменения в системе-источнике' :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=trusteeDocumentNumber :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.DeathInfo :: field=sourceChannelRequisites :: field_documentation_summary_substring :: doc='Реквизиты источника данных о смерти' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.DeathCertificate :: field=comment :: field_documentation_summary_substring :: doc='Реквизиты врачебного свидетельства, констатирующего смерть' :: inbound=False

## 20. Средняя длительность визита/консультации
- 830 term='длительност' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvent :: field=eventCount :: field_documentation_summary_substring :: doc='Количество событий данной длительности просрочки в соответствующий год' :: inbound=True
- 830 term='длительност' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvents :: field=eventCount :: field_documentation_summary_substring :: doc='Количество событий данной длительности просрочки в соответствующий год' :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=trusteeDocumentNumber :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.DeathInfo :: field=sourceChannelRequisites :: field_documentation_summary_substring :: doc='Реквизиты источника данных о смерти' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.DeathCertificate :: field=comment :: field_documentation_summary_substring :: doc='Реквизиты врачебного свидетельства, констатирующего смерть' :: inbound=False

## 21. Активность в мобильном приложении: сессии, глубина
- 940 term='mobile' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.PhoneNumber :: field=mobileOperator :: field_name_prefix :: doc=None :: inbound=True
- 940 term='mobile' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.contact.PhoneNumber.Builder :: field=mobileOperator :: field_name_prefix :: doc=None :: inbound=False
- 940 term='mobile' scope=all_declared_types :: com.sbt.bm.ucp.retail.mbc.model.MbcRequest :: field=mobileOperator :: field_name_prefix :: doc='Мобильный оператор' :: inbound=False
- 910 term='мобильн' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.PhoneNumber :: field=mobileOperator :: field_documentation_display_name_prefix :: doc=None :: inbound=True
- 910 term='мобильн' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPhoneNumber :: field=phoneType :: field_documentation_description_prefix :: doc='Тип телефона' :: inbound=True
- 910 term='мобильн' scope=all_declared_types :: com.sbt.bm.ucp.retail.mbc.model.MbcRequest :: field=mobileOperator :: field_documentation_summary_prefix :: doc='Мобильный оператор' :: inbound=False
- 830 term='активност' scope=projected :: com.sbt.bm.ucp.common.model.unsuspect.PartyUnsuspect :: field=active :: field_documentation_summary_substring :: doc='Признак активности' :: inbound=False
- 830 term='активност' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockInfo :: field=deactivated :: field_documentation_summary_substring :: doc='Признак активности блокировки' :: inbound=True
- 830 term='активност' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity :: field=deactivated :: field_documentation_summary_substring :: doc='Признак активности блокировки' :: inbound=False
- 800 term='mobile' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpMobileOperator :: field=None :: type_name_substring :: doc='Справочник Мобильный оператор' :: inbound=True

## 22. Просмотренные, но не купленные продукты в цифре
- 940 term='product' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.PartyRelatedRole :: field=productRelation :: field_name_prefix :: doc='Типы отношений' :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.galo.common.GaloRelatedProduct :: field=productType :: field_name_prefix :: doc=None :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=productNumber :: field_name_prefix :: doc='Номер заявки на продукт' :: inbound=False
- 940 term='product' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=productInfo :: field_name_prefix :: doc='Информация о продуктах клиента' :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=productCode :: field_name_prefix :: doc=None :: inbound=False
- 940 term='product' scope=all_declared_types :: com.sbt.bm.ucp.galo.common.GaloRelatedProduct.Builder :: field=productType :: field_name_prefix :: doc=None :: inbound=False
- 940 term='product' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=productNumber :: field_name_prefix :: doc=None :: inbound=False
- 780 term='view' scope=all_declared_types :: com.sbt.bm.ucp.utils.diff.UcpDiffUtils :: field=None :: type_documentation_summary_substring :: doc='Allows to calculate diffs of objects and return new tree with nodes, which have differences between left and right entities. <p> If substructure was changed, it will be include in result with {@link DiffDescription#leftValue}, {@link DiffDescription#rightValue} and corresponding {@link Status} and all ancestors will change their own status to {@link Status#DIFFERENCE}. <p> If node contained in left object and not in right, node with all its children will include in result with {@link Status#EXIST_ONLY_IN_LEFT}. If node contained in right and not in left - it will included with {@link Status#EXIST_ONLY_IN_RIGHT} <p> Also user can specify view of Diffs by {@link DiffDescriptionFactory}' :: inbound=False

## 23. Брошенные заявки / незавершённые оформления
- 940 term='processing' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=processingCompleted :: field_name_prefix :: doc='Признак поднятия анкеты на фронте' :: inbound=False
- 940 term='processing' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=processingCompleted :: field_name_prefix :: doc=None :: inbound=False
- 890 term='анкета заявителя' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=None :: type_documentation_summary_prefix :: doc='Анкета заявителя на продукт' :: inbound=False
- 890 term='заявк' scope=all_declared_types :: com.sbt.ucp.unconfirmed.model.PassportValidityCheckElgoOrder :: field=None :: type_documentation_summary_prefix :: doc='Заявка на проверку действительности паспорта в ЭлГО' :: inbound=True
- 880 term='application' scope=all_declared_types :: com.sbt.bm.ucp.cp.model.CreditPotentialApplication :: field=dateApplication :: field_name_substring :: doc='Дата сохранения анкеты в КП' :: inbound=False
- 880 term='application' scope=all_declared_types :: com.sbt.bm.ucp.cp.model.CreditPotentialApplication.Builder :: field=dateApplication :: field_name_substring :: doc=None :: inbound=False
- 830 term='заявк' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=productNumber :: field_documentation_summary_substring :: doc='Номер заявки на продукт' :: inbound=False
- 830 term='заявк' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.PartyModRq :: field=requestNumber :: field_documentation_summary_substring :: doc='Номер заявки во внешней системе' :: inbound=False
- 830 term='заявк' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity :: field=requestNumber :: field_documentation_summary_substring :: doc='Номер заявки во внешней системе' :: inbound=False
- 830 term='заявк' scope=all_declared_types :: com.sbt.bm.ucp.cp.model.CreditPotentialApplication :: field=value :: field_documentation_summary_substring :: doc='Данные кредитной заявки' :: inbound=False

## 24. Реакция на пуши и баннеры (открытия, клики, скрытия)

## 25. Использование банкоматов и УС

## 26. Число обращений в КЦ за период
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ContactUsageType :: field=contactSubType :: field_name_prefix :: doc='Подтип клиента' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ElectronicAddressSubType :: field=contactSubType :: field_name_prefix :: doc='Подтип контакта' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.SystemAuthorisedStatus :: field=contactStatus :: field_name_prefix :: doc='Допустимый статус контактов' :: inbound=False
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.Address :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.ElectronicAddress :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=True
- 940 term='contact' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.contact.AbstractContact :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=False
- 830 term='КЦ' scope=projected :: com.sbt.bm.ucp.common.model.party.extension.UndefinedValue :: field=entityId :: field_documentation_summary_substring :: doc='Идентификатор записи в коллекции' :: inbound=False
- 780 term='КЦ' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractPartyToPartyGroup :: field=None :: type_documentation_summary_substring :: doc='Абстракция для отображения связи клиента с группами' :: inbound=True

## 27. Признак самостоятельности решений (сам оформляет vs просит помощь)

## 28. Каналы, где клиент отказывается от коммуникации
- 1000 term='consent' scope=projected :: com.sbt.bm.ucp.common.model.party.Consent :: field=None :: type_name_exact :: doc='Согласия клиента' :: inbound=True
- 1000 term='consent' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Consent :: field=None :: type_name_exact :: doc='Согласия клиента' :: inbound=True
- 990 term='consent' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=consent :: field_name_exact :: doc=None :: inbound=False
- 990 term='consent' scope=all_declared_types :: com.sbt.bm.ucp.fatca.model.Fatca.Builder :: field=consent :: field_name_exact :: doc=None :: inbound=False
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.common.model.party.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 940 term='consent' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=consents :: field_name_prefix :: doc='Согласия клиента' :: inbound=True
- 940 term='consent' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.Consent.Builder :: field=consentChannels :: field_name_prefix :: doc=None :: inbound=False
- 930 term='consent' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ConsentChannelType :: field=None :: type_name_prefix :: doc='Канал (для которого получено согласие на рассылку)' :: inbound=False
- 910 term='соглас' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=consent :: field_documentation_display_name_prefix :: doc=None :: inbound=False

## 29. Продуктовый холдинг (что уже есть)
- 970 term='информация о продуктах клиента' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=productInfo :: field_documentation_summary_exact :: doc='Информация о продуктах клиента' :: inbound=True
- 960 term='информация о продуктах клиента' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.ProductInfo :: field=None :: type_documentation_summary_exact :: doc='Информация о продуктах клиента' :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.PartyRelatedRole :: field=productRelation :: field_name_prefix :: doc='Типы отношений' :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.galo.common.GaloRelatedProduct :: field=productType :: field_name_prefix :: doc=None :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=productNumber :: field_name_prefix :: doc='Номер заявки на продукт' :: inbound=False
- 940 term='product' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=productInfo :: field_name_prefix :: doc='Информация о продуктах клиента' :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=productCode :: field_name_prefix :: doc=None :: inbound=False
- 940 term='product' scope=all_declared_types :: com.sbt.bm.ucp.galo.common.GaloRelatedProduct.Builder :: field=productType :: field_name_prefix :: doc=None :: inbound=False
- 940 term='product' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=productNumber :: field_name_prefix :: doc=None :: inbound=False

## 30. Остатки по продуктам
- 830 term='остаток' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=obligationCurrent :: field_documentation_summary_substring :: doc='Общий остаток задолженности' :: inbound=True

## 31. Даты открытия и закрытия продуктов
- 940 term='open' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=openBankingRecords :: field_name_prefix :: doc='Дополнительные атрибуты' :: inbound=True
- 940 term='open' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=openDate :: field_name_prefix :: doc=None :: inbound=False
- 940 term='open' scope=projected :: com.sbt.bm.ucp.smpr.Category :: field=openingDate :: field_name_prefix :: doc=None :: inbound=True
- 940 term='open' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks.Builder :: field=openBankingRecords :: field_name_prefix :: doc=None :: inbound=False
- 940 term='open' scope=all_declared_types :: com.sbt.bm.ucp.smpr.Category.Builder :: field=openingDate :: field_name_prefix :: doc=None :: inbound=False
- 940 term='close' scope=projected :: com.sbt.bm.ucp.customerknowledge.model.MergeCustomerKnowledgeInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='close' scope=projected :: com.sbt.bm.ucp.fatca.model.MergeFatcaInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='close' scope=projected :: com.sbt.bm.ucp.markup.model.MergeMarkupInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='close' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=closeDate :: field_name_prefix :: doc=None :: inbound=False
- 940 term='close' scope=all_declared_types :: com.sbt.bm.storage.model.MergeOmniMemoryFactsInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True

## 32. Закрытые продукты и причина закрытия
- 940 term='close' scope=projected :: com.sbt.bm.ucp.customerknowledge.model.MergeCustomerKnowledgeInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='close' scope=projected :: com.sbt.bm.ucp.fatca.model.MergeFatcaInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='close' scope=projected :: com.sbt.bm.ucp.markup.model.MergeMarkupInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='close' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=closeDate :: field_name_prefix :: doc=None :: inbound=False
- 940 term='close' scope=all_declared_types :: com.sbt.bm.storage.model.MergeOmniMemoryFactsInfo :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='close' scope=all_declared_types :: com.sbt.bm.storage.model.MergeOmniMemoryFactsInfo.Builder :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=False
- 940 term='close' scope=all_declared_types :: com.sbt.bm.ucp.customerknowledge.model.MergeCustomerKnowledgeInfo.Builder :: field=closedPartyId :: field_name_prefix :: doc=None :: inbound=False
- 890 term='причины окончания' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.PartyAgreementEndReason :: field=None :: type_documentation_summary_prefix :: doc='Причины окончания действия связей клиента с продуктами/договорами' :: inbound=False

## 33. Ежемесячные обороты по картам
- 880 term='amount' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.insurance.InsurancePaymentAmount :: field=insurancePaymentAmount :: field_name_substring :: doc='Сумма страхового взноса' :: inbound=True
- 880 term='amount' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.insurance.InsurancePaymentAmount.Builder :: field=insurancePaymentAmount :: field_name_substring :: doc=None :: inbound=False
- 880 term='amount' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.insurance.InsurancePaymentOrganizationIncomeSource :: field=insurancePaymentAmounts :: field_name_substring :: doc='Суммы страховых взносов' :: inbound=True
- 880 term='amount' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.insurance.InsurancePaymentOrganizationIncomeSource.Builder :: field=insurancePaymentAmounts :: field_name_substring :: doc=None :: inbound=False
- 880 term='amount' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.insurance.InsurancePaymentPersonIncomeSource :: field=insurancePaymentAmounts :: field_name_substring :: doc='Суммы страховых взносов' :: inbound=True
- 830 term='карта' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=cbCode :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 780 term='карта' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.MigrationCard :: field=None :: type_documentation_display_name_substring :: doc=None :: inbound=False

## 34. Структура трат по категориям
- 910 term='категор' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.QualityCode :: field=category :: field_documentation_summary_prefix :: doc='Категория' :: inbound=True
- 910 term='категор' scope=projected :: com.sbt.bm.ucp.markup.model.MarkupPEP :: field=category407 :: field_documentation_summary_prefix :: doc='Категория 407-П' :: inbound=False
- 910 term='категор' scope=projected :: com.sbt.bm.ucp.markup.model.MarkupRPEP :: field=category407 :: field_documentation_summary_prefix :: doc='Категория 407-П' :: inbound=False
- 910 term='категор' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupPFR :: field=pensionCategory :: field_documentation_summary_prefix :: doc='Категория пенсии' :: inbound=False
- 910 term='категор' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupVipClientCategory :: field=category :: field_documentation_summary_prefix :: doc='Категория VIP-клиента' :: inbound=False
- 880 term='spend' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupPFR :: field=paymentSuspended :: field_name_substring :: doc='Выплата пенсии приостановлена' :: inbound=False
- 880 term='spend' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupPFR.Builder :: field=paymentSuspended :: field_name_substring :: doc=None :: inbound=False

## 35. Регулярные поступления (зарплата, пенсия, аренда)
- 990 term='income' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=income :: field_name_exact :: doc='Среднемесячный доход' :: inbound=False
- 990 term='income' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=income :: field_name_exact :: doc=None :: inbound=False
- 960 term='доход' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.IncomesPayment :: field=None :: type_documentation_display_name_exact :: doc=None :: inbound=True
- 940 term='income' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMaritalInfo :: field=incomeSpouse :: field_name_prefix :: doc='Доход супруга/супруги' :: inbound=True
- 940 term='income' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPlaceOfWork :: field=incomeIdentifications :: field_name_prefix :: doc='Документы о доходе' :: inbound=True
- 940 term='income' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.IncomesPayment :: field=incomeAmount :: field_name_prefix :: doc='Сумма дохода' :: inbound=True
- 940 term='income' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.IncomesPayment.Builder :: field=incomeAmount :: field_name_prefix :: doc=None :: inbound=False
- 940 term='income' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.NdflTwoOrganizationIncomeSource :: field=incomesPayments :: field_name_prefix :: doc='Доходы' :: inbound=True
- 910 term='доход' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMaritalInfo :: field=incomeSpouse :: field_documentation_summary_prefix :: doc='Доход супруга/супруги' :: inbound=True
- 910 term='доход' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.NdflTwoOrganizationIncomeSource :: field=incomesPayments :: field_documentation_summary_prefix :: doc='Доходы' :: inbound=True

## 36. Оценка дохода (модельная)
- 990 term='income' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=income :: field_name_exact :: doc='Среднемесячный доход' :: inbound=False
- 990 term='income' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=income :: field_name_exact :: doc=None :: inbound=False
- 990 term='score' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpInvestorRiskProfileScore :: field=score :: field_name_exact :: doc='Риск-профиль (Целое число 1..5)' :: inbound=True
- 960 term='доход' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.IncomesPayment :: field=None :: type_documentation_display_name_exact :: doc=None :: inbound=True
- 940 term='income' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMaritalInfo :: field=incomeSpouse :: field_name_prefix :: doc='Доход супруга/супруги' :: inbound=True
- 940 term='income' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormPlaceOfWork :: field=incomeIdentifications :: field_name_prefix :: doc='Документы о доходе' :: inbound=True
- 940 term='income' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.IncomesPayment :: field=incomeAmount :: field_name_prefix :: doc='Сумма дохода' :: inbound=True
- 940 term='income' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.IncomesPayment.Builder :: field=incomeAmount :: field_name_prefix :: doc=None :: inbound=False
- 940 term='income' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.NdflTwoOrganizationIncomeSource :: field=incomesPayments :: field_name_prefix :: doc='Доходы' :: inbound=True
- 910 term='доход' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMaritalInfo :: field=incomeSpouse :: field_documentation_summary_prefix :: doc='Доход супруга/супруги' :: inbound=True

## 37. Долговая нагрузка (ПДН) и кредитная история внутри банка
- 1000 term='obligation' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=None :: type_name_exact :: doc='Кредитные обязательства' :: inbound=True
- 970 term='кредитная история' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=creditHistory :: field_documentation_summary_exact :: doc='Кредитная история' :: inbound=True
- 940 term='credit' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=creditHistory :: field_name_prefix :: doc='Кредитная история' :: inbound=True
- 940 term='credit' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=creditCard :: field_name_prefix :: doc=None :: inbound=False
- 940 term='credit' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.ClientRating :: field=creditBureauReport :: field_name_prefix :: doc='Отчет по данным БКИ' :: inbound=False
- 940 term='credit' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.Individual.Builder :: field=creditHistory :: field_name_prefix :: doc=None :: inbound=False
- 940 term='obligation' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.CreditBureauReport :: field=obligations :: field_name_prefix :: doc='Кредитные обязательства' :: inbound=True
- 930 term='credit' scope=projected :: com.sbt.bm.ucp.retail.model.individual.CreditHistory :: field=None :: type_name_prefix :: doc='Кредитная история клиента' :: inbound=True
- 930 term='credit' scope=all_declared_types :: com.sbt.bm.ucp.cp.model.CreditPotential :: field=None :: type_name_prefix :: doc='Кредитный потенциал' :: inbound=False
- 910 term='долг' scope=projected :: com.sbt.bm.ucp.smpr.DeliveryAddress :: field=longitude :: field_documentation_summary_prefix :: doc='Долгота' :: inbound=True

## 38. Просрочки, дефолты, реструктуризации
- 830 term='просроч' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=pastDueEvents :: field_documentation_summary_substring :: doc='События просрочки' :: inbound=True
- 830 term='просроч' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvent :: field=eventCount :: field_documentation_summary_substring :: doc='Количество событий данной длительности просрочки в соответствующий год' :: inbound=True
- 830 term='просроч' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvents :: field=eventCount :: field_documentation_summary_substring :: doc='Количество событий данной длительности просрочки в соответствующий год' :: inbound=False
- 830 term='реструкт' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=wasRestructed :: field_documentation_summary_substring :: doc='Признак проведения реструктуризации' :: inbound=True

## 39. Склонность к риску (инвестпрофиль)
- 970 term='риск-профиль инвестора' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=riskProfile :: field_documentation_summary_exact :: doc='Риск-профиль инвестора' :: inbound=True
- 970 term='риск-профиль инвестора' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupInvestorRiskProfile :: field=investorRiskProfileScore :: field_documentation_summary_exact :: doc='Риск-профиль инвестора' :: inbound=False
- 960 term='риск-профиль инвестора' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=None :: type_documentation_summary_exact :: doc='Риск-профиль инвестора' :: inbound=True
- 940 term='invest' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=investingHorizon :: field_name_prefix :: doc='Горизонт инвестирования' :: inbound=True
- 940 term='invest' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupInvestorRiskProfile :: field=investingHorizon :: field_name_prefix :: doc='Горизонт инвестирования (в месяцах)' :: inbound=False
- 940 term='invest' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile.Builder :: field=investingHorizon :: field_name_prefix :: doc=None :: inbound=False
- 940 term='invest' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupInvestorRiskProfile.Builder :: field=investingHorizon :: field_name_prefix :: doc=None :: inbound=False
- 940 term='risk' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=riskProfile :: field_name_prefix :: doc='Риск-профиль инвестора' :: inbound=True
- 940 term='risk' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks.Builder :: field=riskProfile :: field_name_prefix :: doc=None :: inbound=False
- 930 term='risk' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=None :: type_name_prefix :: doc='Риск-профиль инвестора' :: inbound=True

## 40. Наличие инвестсчетов и опыт инвестирования
- 940 term='purposes' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=purposesOfInvestment :: field_name_prefix :: doc='Цели инвестирования' :: inbound=True
- 940 term='purposes' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile.Builder :: field=purposesOfInvestment :: field_name_prefix :: doc=None :: inbound=False
- 910 term='горизонт инвест' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=investingHorizon :: field_documentation_summary_prefix :: doc='Горизонт инвестирования' :: inbound=True
- 910 term='горизонт инвест' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupInvestorRiskProfile :: field=investingHorizon :: field_documentation_summary_prefix :: doc='Горизонт инвестирования (в месяцах)' :: inbound=False
- 880 term='investment' scope=projected :: com.sbt.bm.ucp.fatca.model.OtherCountryOfTaxResident :: field=programCitizenshipForInvestments :: field_name_substring :: doc='Налоговое резидентство получено по программе гражданство/резидентство в обмен на инвестиции' :: inbound=True
- 880 term='investment' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.PurposeOfInvestment :: field=purposeOfInvestment :: field_name_substring :: doc='Цель инвестирования' :: inbound=True
- 880 term='investment' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=purposesOfInvestment :: field_name_substring :: doc='Цели инвестирования' :: inbound=True
- 880 term='investment' scope=all_declared_types :: com.sbt.bm.ucp.fatca.model.OtherCountryOfTaxResident.Builder :: field=programCitizenshipForInvestments :: field_name_substring :: doc=None :: inbound=False
- 880 term='investment' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.PurposeOfInvestment.Builder :: field=purposeOfInvestment :: field_name_substring :: doc=None :: inbound=False
- 830 term='инвест' scope=projected :: com.sbt.bm.ucp.fatca.model.OtherCountryOfTaxResident :: field=programCitizenshipForInvestments :: field_documentation_summary_substring :: doc='Налоговое резидентство получено по программе гражданство/резидентство в обмен на инвестиции' :: inbound=True

## 41. Сберегательное поведение (регулярность накоплений)

## 42. Отток средств во внешние банки
- 910 term='внешн' scope=projected :: com.sbt.bm.ucp.common.model.party.ManagerEmployeeInfo :: field=externalEmail :: field_documentation_summary_prefix :: doc='Внешний адрес электронной почты (из кадровой системы)' :: inbound=True
- 910 term='внешн' scope=projected :: com.sbt.bm.ucp.smpr.DeliveryAddress :: field=externalId :: field_documentation_summary_prefix :: doc='Внешний идентификатор адреса доставки' :: inbound=True
- 880 term='transfer' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=dataTransferBanned :: field_name_substring :: doc=None :: inbound=False
- 880 term='transfer' scope=all_declared_types :: com.sbt.bm.ucp.fatca.model.Fatca.Builder :: field=dataTransferBanned :: field_name_substring :: doc=None :: inbound=False
- 830 term='внешн' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.EquivalentSystemType :: field=secretName :: field_documentation_summary_substring :: doc='Описание справочника внешних систем' :: inbound=True
- 830 term='внешн' scope=projected :: com.sbt.bm.ucp.common.model.party.equivalent.Equivalent :: field=equivalentGroup :: field_documentation_summary_substring :: doc='Группы идентификаторов внешних систем' :: inbound=True
- 830 term='внешн' scope=projected :: com.sbt.bm.ucp.common.model.party.extension.UndefinedValue :: field=externalSystem :: field_documentation_summary_substring :: doc='Идентификатор внешней системы' :: inbound=False
- 830 term='внешн' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.PartyModRq :: field=requestNumber :: field_documentation_summary_substring :: doc='Номер заявки во внешней системе' :: inbound=False
- 830 term='внешн' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity :: field=requestNumber :: field_documentation_summary_substring :: doc='Номер заявки во внешней системе' :: inbound=False
- 830 term='банк' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.BankruptcyStage :: field=bankruptcyCode :: field_documentation_summary_substring :: doc='Код банкротства' :: inbound=False

## 43. Активность по подпискам и сервисам (СберПрайм и аналоги)
- 910 term='сервис' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpClientInfChangeRbEpkAsApiLink :: field=serviceCode :: field_documentation_summary_prefix :: doc='Сервис SberAPI для автоматизированной системы, с которой ЕПК РБ ведет обмен информацией по клиентам' :: inbound=False
- 910 term='сервис' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Emigration :: field=emigrationServiceAttributes :: field_documentation_summary_prefix :: doc='Сервисные атрибуты гражданства' :: inbound=True
- 890 term='сервис' scope=projected :: com.sbt.bm.ucp.retail.model.individual.EmigrationServiceAttributes :: field=None :: type_documentation_summary_prefix :: doc='Сервисные атрибуты гражданства' :: inbound=True

## 44. Чувствительность к цене/ставке
- 990 term='rate' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=rate :: field_name_exact :: doc='Ставка по обязательству' :: inbound=True
- 930 term='price' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.PriceLevel :: field=None :: type_name_prefix :: doc='Ценовой уровень клиента' :: inbound=False
- 910 term='ставк' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=rate :: field_documentation_summary_prefix :: doc='Ставка по обязательству' :: inbound=True
- 880 term='rate' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.QualityCode :: field=statusForCorporate :: field_name_substring :: doc='Статус проверки для ЮЛ' :: inbound=True
- 880 term='rate' scope=projected :: com.sbt.bm.ucp.common.model.party.ManagerEmployeeInfo :: field=corporateCRM :: field_name_substring :: doc='Система ВКО - Корпоративный CRM' :: inbound=True
- 880 term='rate' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.ManagerEmployeeInfo.Builder :: field=corporateCRM :: field_name_substring :: doc=None :: inbound=False
- 880 term='price' scope=all_declared_types :: com.sbt.bm.ucp.galo.valuation.GaloValuationEntity :: field=actualPrice :: field_name_substring :: doc=None :: inbound=False
- 880 term='price' scope=all_declared_types :: com.sbt.bm.ucp.galo.valuation.GaloValuationEntity.Builder :: field=actualPrice :: field_name_substring :: doc=None :: inbound=False
- 830 term='ставк' scope=projected :: com.sbt.bm.ucp.smpr.DeliveryAddress :: field=externalId :: field_documentation_summary_substring :: doc='Внешний идентификатор адреса доставки' :: inbound=True

## 45. Life-event маркеры (свадьба, рождение ребёнка, переезд, смена работы)
- 830 term='рожд' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=birthCountry :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 830 term='рожд' scope=projected :: com.sbt.bm.ucp.markup.model.RelationPEPInfo :: field=dobPEP :: field_documentation_summary_substring :: doc='Дата рождения из перечня' :: inbound=True
- 830 term='рожд' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=birthDate :: field_documentation_summary_substring :: doc='Дата рождения' :: inbound=False
- 830 term='рожд' scope=projected :: com.sbt.bm.ucp.retail.model.individual.BirthPlace :: field=birthPlace :: field_documentation_summary_substring :: doc='Стандартизованное место рождения одной строкой' :: inbound=True
- 830 term='рожд' scope=projected :: com.sbt.bm.ucp.retail.model.individual.BirthPlaceServiceAttributes :: field=birthPlaceQualityCode :: field_documentation_summary_substring :: doc='Код качества места рождения' :: inbound=True

## 46. Ценность клиента (LTV / доходность)

## 47. Предпочтительный канал коммуникации
- 1000 term='channel' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.Channel :: field=None :: type_name_exact :: doc='Канал (для которого получено согласие на рассылку)' :: inbound=True
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.common.model.party.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 970 term='канал' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Consent :: field=consentChannels :: field_documentation_summary_exact :: doc='Канал' :: inbound=True
- 940 term='preferred' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney :: field=preferredLanguages :: field_name_prefix :: doc='Предпочитаемые языки коммуникации' :: inbound=False
- 940 term='preferred' scope=projected :: com.sbt.bm.ucp.customerjourney.model.PreferredLanguage :: field=preferredLanguage :: field_name_prefix :: doc='Предпочитаемый язык общения' :: inbound=True
- 940 term='preferred' scope=all_declared_types :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney.Builder :: field=preferredLanguages :: field_name_prefix :: doc=None :: inbound=False
- 940 term='preferred' scope=all_declared_types :: com.sbt.bm.ucp.customerjourney.model.PreferredLanguage.Builder :: field=preferredLanguage :: field_name_prefix :: doc=None :: inbound=False
- 940 term='channel' scope=all_declared_types :: com.sbt.bm.storage.model.OmniMemoryFact :: field=channelId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='channel' scope=all_declared_types :: com.sbt.bm.storage.model.OmniMemoryFact.Builder :: field=channelId :: field_name_prefix :: doc=None :: inbound=False
- 910 term='предпочитаем' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney :: field=preferredLanguages :: field_documentation_summary_prefix :: doc='Предпочитаемые языки коммуникации' :: inbound=False

## 48. Предпочтительное время контакта
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney :: field=versionStartDate :: field_documentation_summary_prefix :: doc='Время изменения в клиентском модуле' :: inbound=False
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.DistantClientManager :: field=endDate :: field_documentation_summary_prefix :: doc='Время деактивации записи' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.EmploymentInfo :: field=versionStartDate :: field_documentation_summary_prefix :: doc='Время изменения в клиентском модуле' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.PreferredLanguage :: field=updateDateTime :: field_documentation_summary_prefix :: doc='Время изменения в источнике' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=updateDateTime :: field_documentation_summary_prefix :: doc='Время изменения в системе-источнике' :: inbound=False
- 830 term='доступности клиента' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Preferences :: field=customerAvailabilityTime :: field_documentation_summary_substring :: doc='Интервал доступности клиента' :: inbound=True
- 830 term='контакт' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ElectronicAddressSubType :: field=contactSubType :: field_documentation_summary_substring :: doc='Подтип контакта' :: inbound=True
- 830 term='контакт' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.SystemAuthorisedStatus :: field=contactStatus :: field_documentation_summary_substring :: doc='Допустимый статус контактов' :: inbound=False
- 830 term='контакт' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.Address :: field=contactServiceAttributes :: field_documentation_summary_substring :: doc='Служебные атрибуты адресов и контактов' :: inbound=True
- 830 term='контакт' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.ElectronicAddress :: field=contactServiceAttributes :: field_documentation_summary_substring :: doc='Служебные атрибуты адресов и контактов' :: inbound=True

## 49. Предпочтительная тональность (формальная/дружеская)
- 910 term='предпочтен' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=preferences :: field_documentation_summary_prefix :: doc='Предпочтения клиента' :: inbound=True
- 890 term='предпочтен' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Preferences :: field=None :: type_documentation_summary_prefix :: doc='Предпочтения клиента' :: inbound=True
- 800 term='friendly' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpUnfriendlyRFCountry :: field=None :: type_name_substring :: doc='Справочник недружественных РФ стран' :: inbound=False

## 50. Предпочтительный формат контента (текст / цифры / визуал / короткое видео)
- 910 term='предпочтен' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=preferences :: field_documentation_summary_prefix :: doc='Предпочтения клиента' :: inbound=True
- 890 term='предпочтен' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Preferences :: field=None :: type_documentation_summary_prefix :: doc='Предпочтения клиента' :: inbound=True

## 51. Допустимая длина сообщения / объём информации
- 990 term='message' scope=all_declared_types :: com.sbt.bm.ucp.change_control.api.api_result.ApiResultError :: field=message :: field_name_exact :: doc='Represents an error occurred during request processing. This class is immutable and thread-safe by design.' :: inbound=True

## 52. Уровень финансовой грамотности
- 1000 term='literacy' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Literacy :: field=None :: type_name_exact :: doc='Неграмотнось' :: inbound=True
- 990 term='literacy' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=literacy :: field_name_exact :: doc='Неграмотность' :: inbound=True
- 990 term='literacy' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.Individual.Builder :: field=literacy :: field_name_exact :: doc=None :: inbound=False
- 990 term='literacy' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.Literacy.Builder :: field=literacy :: field_name_exact :: doc=None :: inbound=False
- 910 term='финансов' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=welfare :: field_documentation_summary_prefix :: doc='Финансовое положение' :: inbound=True
- 890 term='финансов' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.FinData :: field=None :: type_documentation_display_name_prefix :: doc=None :: inbound=False
- 830 term='грамот' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=literacy :: field_documentation_summary_substring :: doc='Неграмотность' :: inbound=True
- 780 term='финансов' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.FinancialInstituteCode :: field=None :: type_documentation_summary_substring :: doc='Коды финансовых институтов' :: inbound=False
- 780 term='финансов' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.Welfare :: field=None :: type_documentation_summary_substring :: doc='Благосостояние (финансовое положение)' :: inbound=True
- 780 term='грамот' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Literacy :: field=None :: type_documentation_summary_substring :: doc='Неграмотнось' :: inbound=True

## 53. Порог назойливости (частота касаний без раздражения)
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ContactUsageType :: field=contactSubType :: field_name_prefix :: doc='Подтип клиента' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ElectronicAddressSubType :: field=contactSubType :: field_name_prefix :: doc='Подтип контакта' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.SystemAuthorisedStatus :: field=contactStatus :: field_name_prefix :: doc='Допустимый статус контактов' :: inbound=False
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.Address :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.ElectronicAddress :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=True
- 940 term='contact' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.contact.AbstractContact :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=False

## 54. Реакция на предыдущие форматы подачи
- 800 term='response' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockResponse :: field=None :: type_name_substring :: doc='Ответ на запрос резервирования клиента для редактирования' :: inbound=False

## 55. Триггерные и запрещённые темы (чувствительные формулировки)
- 780 term='запрещ' scope=projected :: com.sbt.bm.ucp.common.model.unsuspect.PartyUnsuspect :: field=None :: type_documentation_summary_substring :: doc='Клиенты, запрещенные к слиянию' :: inbound=False

## 56. Психотип клиента

## 57. Стиль принятия решений (импульсивный / аналитический / консультативный)
- 910 term='аналитич' scope=projected :: com.sbt.bm.ucp.common.model.party.extension.PartyServiceAttributes :: field=reliabilitySignAnalytical :: field_documentation_summary_prefix :: doc='Аналитический признак достоверности' :: inbound=True
- 880 term='decision' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.GreenCard :: field=residenceDecisionDate :: field_name_substring :: doc=None :: inbound=False
- 880 term='decision' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.identification.GreenCard.Builder :: field=residenceDecisionDate :: field_name_substring :: doc=None :: inbound=False

## 58. Скорость принятия решения
- 880 term='decision' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.GreenCard :: field=residenceDecisionDate :: field_name_substring :: doc=None :: inbound=False
- 880 term='decision' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.identification.GreenCard.Builder :: field=residenceDecisionDate :: field_name_substring :: doc=None :: inbound=False
- 830 term='решени' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.GreenCard :: field=residenceDecisionDate :: field_documentation_display_name_substring :: doc=None :: inbound=False

## 59. Отношение к риску (психологическое, не инвестпрофиль)
- 910 term='риск' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpInvestorRiskProfileScore :: field=score :: field_documentation_summary_prefix :: doc='Риск-профиль (Целое число 1..5)' :: inbound=True
- 910 term='риск' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=riskProfile :: field_documentation_summary_prefix :: doc='Риск-профиль инвестора' :: inbound=True
- 910 term='риск' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupInvestorRiskProfile :: field=investorRiskProfileScore :: field_documentation_summary_prefix :: doc='Риск-профиль инвестора' :: inbound=False
- 890 term='риск' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=None :: type_documentation_summary_prefix :: doc='Риск-профиль инвестора' :: inbound=True
- 830 term='риск' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Recommendation :: field=factorName :: field_documentation_summary_substring :: doc='Наименование фактора риска' :: inbound=True
- 780 term='риск' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupHighRisk :: field=None :: type_documentation_summary_substring :: doc='Повышенная степень риска' :: inbound=False

## 60. Доверие к банку / уровень скепсиса
- 940 term='trust' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=trustee :: field_name_prefix :: doc=None :: inbound=False
- 940 term='trust' scope=all_declared_types :: com.sbt.bm.ucp.fatca.model.Fatca.Builder :: field=trustee :: field_name_prefix :: doc=None :: inbound=False

## 61. Мотивационные драйверы (экономия, статус, безопасность, удобство, забота о близких)
- 990 term='driver' scope=projected :: com.sbt.bm.ucp.smpr.VehicleDriver :: field=driver :: field_name_exact :: doc=None :: inbound=True
- 990 term='driver' scope=all_declared_types :: com.sbt.bm.ucp.smpr.VehicleDriver.Builder :: field=driver :: field_name_exact :: doc=None :: inbound=False
- 940 term='driver' scope=projected :: com.sbt.bm.ucp.smpr.RelatedDriver :: field=driverId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='driver' scope=all_declared_types :: com.sbt.bm.ucp.smpr.RelatedDriver.Builder :: field=driverId :: field_name_prefix :: doc=None :: inbound=False
- 880 term='driver' scope=projected :: com.sbt.bm.ucp.smpr.SmartProfile :: field=vehicleDrivers :: field_name_substring :: doc=None :: inbound=True
- 880 term='driver' scope=projected :: com.sbt.bm.ucp.smpr.Vehicle :: field=relatedDrivers :: field_name_substring :: doc=None :: inbound=True
- 800 term='driver' scope=projected :: com.sbt.bm.ucp.smpr.VehicleDriverUserInfo :: field=None :: type_name_substring :: doc=None :: inbound=True

## 62. Персотеги SberNBA
- 1000 term='marker' scope=projected :: com.sbt.bm.ucp.customerknowledge.model.Marker :: field=None :: type_name_exact :: doc=None :: inbound=True
- 990 term='tag' scope=projected :: com.sbt.bm.ucp.galo.common.GaloTag :: field=tag :: field_name_exact :: doc=None :: inbound=True
- 990 term='tag' scope=projected :: com.sbt.bm.ucp.smpr.DeliveryAddress :: field=tag :: field_name_exact :: doc='Тег' :: inbound=True
- 990 term='tag' scope=all_declared_types :: com.sbt.bm.ucp.galo.common.GaloTag.Builder :: field=tag :: field_name_exact :: doc=None :: inbound=False
- 990 term='tag' scope=all_declared_types :: com.sbt.bm.ucp.smpr.DeliveryAddress.Builder :: field=tag :: field_name_exact :: doc=None :: inbound=False
- 940 term='marker' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpFrontEndClientMarker :: field=markerGroup :: field_name_prefix :: doc='Группа маркеров' :: inbound=True
- 940 term='marker' scope=projected :: com.sbt.bm.ucp.customerknowledge.model.CustomerKnowledge :: field=markers :: field_name_prefix :: doc='Маркеры клиенты' :: inbound=False
- 940 term='marker' scope=all_declared_types :: com.sbt.bm.ucp.customerknowledge.model.CustomerKnowledge.Builder :: field=markers :: field_name_prefix :: doc=None :: inbound=False
- 940 term='tag' scope=projected :: com.sbt.bm.ucp.galo.realestate.GaloRealEstateEntity :: field=tags :: field_name_prefix :: doc=None :: inbound=False
- 940 term='tag' scope=projected :: com.sbt.bm.ucp.galo.vehicle.GaloVehicleEntity :: field=tags :: field_name_prefix :: doc=None :: inbound=False

## 63. Интересы и увлечения
- 990 term='hobby' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.AbstractMarketingInfo :: field=hobby :: field_name_exact :: doc='Тип увлечения' :: inbound=False
- 990 term='hobby' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Movies :: field=hobby :: field_name_exact :: doc='Тип увлечения' :: inbound=False
- 990 term='hobby' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Movies.Builder :: field=hobby :: field_name_exact :: doc=None :: inbound=False
- 990 term='hobby' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Music :: field=hobby :: field_name_exact :: doc='Тип увлечения' :: inbound=False
- 990 term='hobby' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Music.Builder :: field=hobby :: field_name_exact :: doc=None :: inbound=False
- 930 term='hobby' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.HobbyType :: field=None :: type_name_prefix :: doc=None :: inbound=True
- 830 term='увлечен' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.AbstractMarketingInfo :: field=hobby :: field_documentation_summary_substring :: doc='Тип увлечения' :: inbound=False
- 830 term='увлечен' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Movies :: field=hobby :: field_documentation_summary_substring :: doc='Тип увлечения' :: inbound=False
- 830 term='увлечен' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Music :: field=hobby :: field_documentation_summary_substring :: doc='Тип увлечения' :: inbound=False
- 830 term='увлечен' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.Travelling :: field=hobby :: field_documentation_summary_substring :: doc='Тип увлечения' :: inbound=False

## 64. Визуальные предпочтения (в т.ч. «любимый цвет»)
- 910 term='предпочтен' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=preferences :: field_documentation_summary_prefix :: doc='Предпочтения клиента' :: inbound=True
- 890 term='предпочтен' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Preferences :: field=None :: type_documentation_summary_prefix :: doc='Предпочтения клиента' :: inbound=True

## 65. Стиль речи клиента (по транскрибации)

## 66. Кластер/группа клиента (результат паттерн-майнера)
- 960 term='группы клиентов' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.PartyGroup :: field=None :: type_documentation_summary_exact :: doc='Группы клиентов' :: inbound=True
- 910 term='групп' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ContactFlagType :: field=group :: field_documentation_summary_prefix :: doc='Группа' :: inbound=True
- 910 term='групп' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ContactGroup :: field=parentGroup :: field_documentation_summary_prefix :: doc='Группа' :: inbound=True
- 910 term='групп' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.QualityCode :: field=qualityCodeGroup :: field_documentation_summary_prefix :: doc='Группа кода качества' :: inbound=True
- 910 term='групп' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpFrontEndClientMarker :: field=markerGroup :: field_documentation_summary_prefix :: doc='Группа маркеров' :: inbound=True
- 910 term='групп' scope=projected :: com.sbt.bm.ucp.common.model.party.ContactToContactGroup :: field=contactGroup :: field_documentation_summary_prefix :: doc='Группа контактов' :: inbound=True
- 910 term='групп' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractPartyToPartyGroup :: field=partyGroup :: field_documentation_summary_prefix :: doc='Группа' :: inbound=True

## 67. Журнал визитов в ВСП: дата, цель визита
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=trusteeDocumentNumber :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.DeathInfo :: field=sourceChannelRequisites :: field_documentation_summary_substring :: doc='Реквизиты источника данных о смерти' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.DeathCertificate :: field=comment :: field_documentation_summary_substring :: doc='Реквизиты врачебного свидетельства, констатирующего смерть' :: inbound=False
- 800 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney :: field=None :: type_name_substring :: doc=None :: inbound=False
- 800 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourneyMergeRecord :: field=None :: type_name_substring :: doc=None :: inbound=True
- 740 term='journey' scope=all_declared_types :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney.Builder :: field=mergeRecords :: field_type_substring :: doc=None :: inbound=False
- 700 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.DistantClientManager :: field=None :: type_fqcn_substring :: doc=None :: inbound=True
- 700 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.EmploymentInfo :: field=None :: type_fqcn_substring :: doc=None :: inbound=True
- 700 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.PreferredLanguage :: field=None :: type_fqcn_substring :: doc=None :: inbound=True
- 700 term='journey' scope=all_declared_types :: com.sbt.bm.ucp.customerjourney.model.CustomerJourneyMergeRecord.Builder :: field=None :: type_fqcn_substring :: doc=None :: inbound=False

## 68. Выполненные шаги продажи по визитам
- 800 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney :: field=None :: type_name_substring :: doc=None :: inbound=False
- 800 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourneyMergeRecord :: field=None :: type_name_substring :: doc=None :: inbound=True
- 740 term='journey' scope=all_declared_types :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney.Builder :: field=mergeRecords :: field_type_substring :: doc=None :: inbound=False
- 700 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.DistantClientManager :: field=None :: type_fqcn_substring :: doc=None :: inbound=True
- 700 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.EmploymentInfo :: field=None :: type_fqcn_substring :: doc=None :: inbound=True
- 700 term='journey' scope=projected :: com.sbt.bm.ucp.customerjourney.model.PreferredLanguage :: field=None :: type_fqcn_substring :: doc=None :: inbound=True
- 700 term='journey' scope=all_declared_types :: com.sbt.bm.ucp.customerjourney.model.CustomerJourneyMergeRecord.Builder :: field=None :: type_fqcn_substring :: doc=None :: inbound=False

## 69. Что предлагали и как консультировали

## 70. Результат каждого предложения (принял / отказал / отложил)
- 910 term='результат' scope=projected :: com.sbt.bm.ucp.markup.model.MatchingHistory :: field=resultCheck :: field_documentation_summary_prefix :: doc='Результат проверки' :: inbound=True
- 910 term='отказ' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=refusingType :: field_documentation_display_name_prefix :: doc=None :: inbound=False
- 830 term='результат' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourneyMergeRecord :: field=deactivatedPartyId :: field_documentation_summary_substring :: doc='Идентификатор деактивированного в результате слияния профиля клиента' :: inbound=True
- 830 term='результат' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMergeRecord :: field=deactivatedPartyId :: field_documentation_summary_substring :: doc='Идентификатор деактивированного в результате слияния профиля клиента' :: inbound=True
- 830 term='результат' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=unmergeErrorClientInfo :: field_documentation_summary_substring :: doc='Информация о клиенте, полученном в результате ошибочного слияния' :: inbound=True
- 830 term='результат' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=unmergeErrorClientInfo :: field_documentation_summary_substring :: doc='Информация о клиенте, полученном в результате ошибочного слияния' :: inbound=False
- 830 term='отказ' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupAccessibility :: field=refusedToProvide :: field_documentation_summary_substring :: doc='Клиент отказался от предоставления сведений по специальным потребностям' :: inbound=False
- 780 term='отказ' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.RefusingDocument :: field=None :: type_documentation_summary_substring :: doc='Виды документов, подтверждающих отказ от гражданства США' :: inbound=True
- 780 term='отказ' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.RefusingType :: field=None :: type_documentation_summary_substring :: doc='Виды отказов от гражданства США' :: inbound=True

## 71. Формулировки отказов и их причины
- 910 term='отказ' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=refusingType :: field_documentation_display_name_prefix :: doc=None :: inbound=False
- 910 term='причин' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.Inn :: field=changeReason :: field_documentation_summary_prefix :: doc='Причина изменения данных' :: inbound=False
- 910 term='причин' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.OtherDocument :: field=changeReason :: field_documentation_summary_prefix :: doc='Причина изменения данных' :: inbound=False
- 910 term='причин' scope=projected :: com.sbt.bm.ucp.fatca.model.OtherCountryOfTaxResident :: field=inAbsenceReason :: field_documentation_summary_prefix :: doc='Причина отсутствия ИН' :: inbound=True
- 910 term='причин' scope=projected :: com.sbt.bm.ucp.fatca.model.QuestionBlock :: field=inCountryAbsenceReason :: field_documentation_display_name_prefix :: doc=None :: inbound=True
- 910 term='причин' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormIdentification :: field=comment :: field_documentation_summary_prefix :: doc='Причина Изменения' :: inbound=True
- 910 term='причин' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.identificatation.AbstractIdentification :: field=changeReason :: field_documentation_summary_prefix :: doc='Причина изменения данных' :: inbound=True
- 830 term='отказ' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupAccessibility :: field=refusedToProvide :: field_documentation_summary_substring :: doc='Клиент отказался от предоставления сведений по специальным потребностям' :: inbound=False
- 780 term='отказ' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.RefusingDocument :: field=None :: type_documentation_summary_substring :: doc='Виды документов, подтверждающих отказ от гражданства США' :: inbound=True
- 780 term='отказ' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.RefusingType :: field=None :: type_documentation_summary_substring :: doc='Виды отказов от гражданства США' :: inbound=True

## 72. Библиотека возражений клиента

## 73. Как возражения были отработаны и с каким результатом
- 910 term='результат' scope=projected :: com.sbt.bm.ucp.markup.model.MatchingHistory :: field=resultCheck :: field_documentation_summary_prefix :: doc='Результат проверки' :: inbound=True
- 830 term='результат' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourneyMergeRecord :: field=deactivatedPartyId :: field_documentation_summary_substring :: doc='Идентификатор деактивированного в результате слияния профиля клиента' :: inbound=True
- 830 term='результат' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormMergeRecord :: field=deactivatedPartyId :: field_documentation_summary_substring :: doc='Идентификатор деактивированного в результате слияния профиля клиента' :: inbound=True
- 830 term='результат' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=unmergeErrorClientInfo :: field_documentation_summary_substring :: doc='Информация о клиенте, полученном в результате ошибочного слияния' :: inbound=True
- 830 term='результат' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.AbstractParty :: field=unmergeErrorClientInfo :: field_documentation_summary_substring :: doc='Информация о клиенте, полученном в результате ошибочного слияния' :: inbound=False

## 74. История покупок: продукт, дата, канал, кто продал
- 940 term='product' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.PartyRelatedRole :: field=productRelation :: field_name_prefix :: doc='Типы отношений' :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.galo.common.GaloRelatedProduct :: field=productType :: field_name_prefix :: doc=None :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=productNumber :: field_name_prefix :: doc='Номер заявки на продукт' :: inbound=False
- 940 term='product' scope=projected :: com.sbt.bm.ucp.retail.model.individual.ExtraBlocks :: field=productInfo :: field_name_prefix :: doc='Информация о продуктах клиента' :: inbound=True
- 940 term='product' scope=projected :: com.sbt.bm.ucp.retail.model.way4.CardProduct :: field=productCode :: field_name_prefix :: doc=None :: inbound=False
- 940 term='product' scope=all_declared_types :: com.sbt.bm.ucp.galo.common.GaloRelatedProduct.Builder :: field=productType :: field_name_prefix :: doc=None :: inbound=False
- 940 term='product' scope=all_declared_types :: com.sbt.bm.ucp.preclient.form.model.PreclientForm.Builder :: field=productNumber :: field_name_prefix :: doc=None :: inbound=False

## 75. Транскрибации диалогов «клиент — сотрудник»

## 76. История обращений и жалоб

## 77. История маркетинговых касаний
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ContactUsageType :: field=contactSubType :: field_name_prefix :: doc='Подтип клиента' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ElectronicAddressSubType :: field=contactSubType :: field_name_prefix :: doc='Подтип контакта' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.SystemAuthorisedStatus :: field=contactStatus :: field_name_prefix :: doc='Допустимый статус контактов' :: inbound=False
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.Address :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=True
- 940 term='contact' scope=projected :: com.sbt.bm.ucp.common.model.party.contact.ElectronicAddress :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=True
- 940 term='contact' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.contact.AbstractContact :: field=contactServiceAttributes :: field_name_prefix :: doc='Служебные атрибуты адресов и контактов' :: inbound=False
- 890 term='маркетинг' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.marketinginfo.AbstractMarketingInfo :: field=None :: type_documentation_summary_prefix :: doc='Маркетинговая информация' :: inbound=False

## 78. Динамика склонностей во времени
- 990 term='score' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.UcpInvestorRiskProfileScore :: field=score :: field_name_exact :: doc='Риск-профиль (Целое число 1..5)' :: inbound=True
- 880 term='score' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile :: field=investorRiskProfileScore :: field_name_substring :: doc='Значение риск-профиля' :: inbound=True
- 880 term='score' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupInvestorRiskProfile :: field=investorRiskProfileScore :: field_name_substring :: doc='Риск-профиль инвестора' :: inbound=False
- 880 term='score' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.ClientRating :: field=totalScore :: field_name_substring :: doc='Значение РК' :: inbound=False
- 880 term='score' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.History :: field=totalScore :: field_name_substring :: doc='Значение рейтинга' :: inbound=True
- 880 term='score' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.RiskProfile.Builder :: field=investorRiskProfileScore :: field_name_substring :: doc=None :: inbound=False

## 79. Сценарии, ранее применённые к клиенту, и их итог
- 990 term='result' scope=all_declared_types :: com.sbt.bm.ucp.change_control.api.api_result.ApiResult :: field=result :: field_name_exact :: doc='Represents either result of successfully finished requested UCP API operation or errors occurred during request processing. This class is immutable and thread-safe by design.' :: inbound=False
- 940 term='scenario' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.DeduplicationRule :: field=scenarioWeight :: field_name_prefix :: doc='Справочник правил идентификации дублей' :: inbound=True
- 940 term='result' scope=projected :: com.sbt.bm.ucp.markup.model.MatchingHistory :: field=resultCheck :: field_name_prefix :: doc='Результат проверки' :: inbound=True
- 940 term='result' scope=all_declared_types :: com.sbt.bm.ucp.markup.model.MatchingHistory.Builder :: field=resultCheck :: field_name_prefix :: doc=None :: inbound=False
- 800 term='result' scope=all_declared_types :: com.sbt.bm.ucp.change_control.api.api_result.ApiResultError :: field=None :: type_name_substring :: doc='Represents an error occurred during request processing. This class is immutable and thread-safe by design.' :: inbound=True
- 800 term='result' scope=all_declared_types :: com.sbt.bm.ucp.change_control.api.api_result.ApiResultStatus :: field=None :: type_name_substring :: doc='Represents the status of processed request.' :: inbound=True

## 80. NPS / оценки обслуживания клиентом

## 81. События по клиенту за последние 24–72 часа во всех каналах
- 1000 term='channel' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.Channel :: field=None :: type_name_exact :: doc='Канал (для которого получено согласие на рассылку)' :: inbound=True
- 940 term='channel' scope=all_declared_types :: com.sbt.bm.storage.model.OmniMemoryFact :: field=channelId :: field_name_prefix :: doc=None :: inbound=True
- 940 term='channel' scope=all_declared_types :: com.sbt.bm.storage.model.OmniMemoryFact.Builder :: field=channelId :: field_name_prefix :: doc=None :: inbound=False
- 940 term='event' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvent :: field=eventCount :: field_name_prefix :: doc='Количество событий данной длительности просрочки в соответствующий год' :: inbound=True
- 940 term='event' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvents :: field=eventCount :: field_name_prefix :: doc='Количество событий данной длительности просрочки в соответствующий год' :: inbound=False
- 940 term='event' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.PropagationEntity :: field=eventTypeId :: field_name_prefix :: doc='Ссылка на справочник событий, вызвавших распространение' :: inbound=False
- 940 term='event' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.PropagationEntity.Builder :: field=eventTypeId :: field_name_prefix :: doc=None :: inbound=False
- 910 term='событ' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=pastDueEvents :: field_documentation_summary_prefix :: doc='События просрочки' :: inbound=True
- 890 term='событ' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvent :: field=None :: type_documentation_summary_prefix :: doc='События просрочки' :: inbound=True
- 890 term='событ' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.PastDueEvents :: field=None :: type_documentation_summary_prefix :: doc='События просрочки' :: inbound=False

## 82. Свежие отказы (продукт + канал + время)
- 910 term='отказ' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=refusingType :: field_documentation_display_name_prefix :: doc=None :: inbound=False
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.CustomerJourney :: field=versionStartDate :: field_documentation_summary_prefix :: doc='Время изменения в клиентском модуле' :: inbound=False
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.DistantClientManager :: field=endDate :: field_documentation_summary_prefix :: doc='Время деактивации записи' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.EmploymentInfo :: field=versionStartDate :: field_documentation_summary_prefix :: doc='Время изменения в клиентском модуле' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.customerjourney.model.PreferredLanguage :: field=updateDateTime :: field_documentation_summary_prefix :: doc='Время изменения в источнике' :: inbound=True
- 910 term='время' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=updateDateTime :: field_documentation_summary_prefix :: doc='Время изменения в системе-источнике' :: inbound=False
- 830 term='отказ' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupAccessibility :: field=refusedToProvide :: field_documentation_summary_substring :: doc='Клиент отказался от предоставления сведений по специальным потребностям' :: inbound=False
- 780 term='отказ' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.RefusingDocument :: field=None :: type_documentation_summary_substring :: doc='Виды документов, подтверждающих отказ от гражданства США' :: inbound=True
- 780 term='отказ' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.RefusingType :: field=None :: type_documentation_summary_substring :: doc='Виды отказов от гражданства США' :: inbound=True

## 83. Открытые обращения и незакрытые проблемы
- 940 term='issue' scope=projected :: com.sbt.bm.ucp.common.model.party.extension.IdentificationServiceAttributes :: field=issuedByOrganizationQualityCode :: field_name_prefix :: doc='Код качества организации, выдавшей документ' :: inbound=True
- 940 term='issue' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.Inn :: field=issuedByOrganization :: field_name_prefix :: doc=None :: inbound=False
- 940 term='issue' scope=projected :: com.sbt.bm.ucp.common.model.party.identificatation.OtherDocument :: field=issuedByOrganization :: field_name_prefix :: doc=None :: inbound=False
- 940 term='issue' scope=projected :: com.sbt.bm.ucp.galo.vehicle.GaloVehicleDocument :: field=issuedByOrganization :: field_name_prefix :: doc=None :: inbound=True
- 940 term='issue' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientFormEmploymentRecord :: field=issuedDate :: field_name_prefix :: doc='Дата выдачи' :: inbound=True
- 940 term='issue' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.extension.IdentificationServiceAttributes.Builder :: field=issuedByOrganizationQualityCode :: field_name_prefix :: doc=None :: inbound=False
- 940 term='issue' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.identificatation.AbstractIdentification :: field=issuedByOrganization :: field_name_prefix :: doc=None :: inbound=True
- 940 term='issue' scope=all_declared_types :: com.sbt.bm.ucp.common.model.party.identificatation.Inn.Builder :: field=issuedByOrganization :: field_name_prefix :: doc=None :: inbound=False

## 84. Заявленная цель текущего визита
- 910 term='цель' scope=projected :: com.sbt.bm.ucp.retail.model.individual.extraBlocks.PurposeOfInvestment :: field=purposeOfInvestment :: field_documentation_summary_prefix :: doc='Цель инвестирования' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.fatca.model.Fatca :: field=trusteeDocumentNumber :: field_documentation_display_name_substring :: doc=None :: inbound=False
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.DeathInfo :: field=sourceChannelRequisites :: field_documentation_summary_substring :: doc='Реквизиты источника данных о смерти' :: inbound=True
- 830 term='визит' scope=projected :: com.sbt.bm.ucp.retail.model.individual.identification.DeathCertificate :: field=comment :: field_documentation_summary_substring :: doc='Реквизиты врачебного свидетельства, констатирующего смерть' :: inbound=False

## 85. Операции за последние часы/дни (крупный приход или расход)
- 940 term='payment' scope=projected :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupPFR :: field=paymentSuspended :: field_name_prefix :: doc='Выплата пенсии приостановлена' :: inbound=False
- 940 term='payment' scope=all_declared_types :: com.sbt.bm.ucp.retail.model.individual.partytopartygroup.PartyToPartyGroupPFR.Builder :: field=paymentSuspended :: field_name_prefix :: doc=None :: inbound=False
- 910 term='операц' scope=projected :: com.sbt.bm.ucp.common.model.party.extension.PartyServiceAttributes :: field=reliabilitySignOperational :: field_documentation_summary_prefix :: doc='Операционный признак достоверности' :: inbound=True
- 910 term='сумма' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.insurance.InsurancePaymentAmount :: field=insurancePaymentAmount :: field_documentation_summary_prefix :: doc='Сумма страхового взноса' :: inbound=True
- 910 term='сумма' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl2.IncomesPayment :: field=incomeAmount :: field_documentation_summary_prefix :: doc='Сумма дохода' :: inbound=True
- 910 term='сумма' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl3.BusinessAdvocacyPrivateIncome :: field=incomeAmount :: field_documentation_summary_prefix :: doc='Сумма дохода' :: inbound=True
- 910 term='сумма' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl3.NdflThreeOrganizationIncomeSource :: field=incomeAmount :: field_documentation_summary_prefix :: doc='Сумма дохода' :: inbound=True
- 910 term='сумма' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.ndfl3.NdflThreePersonIncomeSource :: field=incomeAmount :: field_documentation_summary_prefix :: doc='Сумма дохода' :: inbound=True
- 880 term='payment' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=currentRepaymentDate :: field_name_substring :: doc='Текущая дата выполнения обязательств' :: inbound=True
- 880 term='payment' scope=all_declared_types :: com.sbt.bm.ucp.finprofile.model.CalculationOfInsurancePaymentsCertificate :: field=insurancePayment :: field_name_substring :: doc='Страховые взносы' :: inbound=True

## 86. Активные заявки в обработке
- 890 term='заявк' scope=all_declared_types :: com.sbt.ucp.unconfirmed.model.PassportValidityCheckElgoOrder :: field=None :: type_documentation_summary_prefix :: doc='Заявка на проверку действительности паспорта в ЭлГО' :: inbound=True
- 880 term='application' scope=all_declared_types :: com.sbt.bm.ucp.cp.model.CreditPotentialApplication :: field=dateApplication :: field_name_substring :: doc='Дата сохранения анкеты в КП' :: inbound=False
- 880 term='application' scope=all_declared_types :: com.sbt.bm.ucp.cp.model.CreditPotentialApplication.Builder :: field=dateApplication :: field_name_substring :: doc=None :: inbound=False
- 830 term='заявк' scope=projected :: com.sbt.bm.ucp.preclient.form.model.PreclientForm :: field=productNumber :: field_documentation_summary_substring :: doc='Номер заявки на продукт' :: inbound=False
- 830 term='заявк' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.PartyModRq :: field=requestNumber :: field_documentation_summary_substring :: doc='Номер заявки во внешней системе' :: inbound=False
- 830 term='заявк' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity :: field=requestNumber :: field_documentation_summary_substring :: doc='Номер заявки во внешней системе' :: inbound=False
- 830 term='заявк' scope=all_declared_types :: com.sbt.bm.ucp.cp.model.CreditPotentialApplication :: field=value :: field_documentation_summary_substring :: doc='Данные кредитной заявки' :: inbound=False
- 830 term='заявк' scope=all_declared_types :: com.sbt.bm.ucp.creditscore.model.Obligation :: field=obligationNumber :: field_documentation_summary_substring :: doc='Номер договора/карты/заявки' :: inbound=True
- 780 term='обработ' scope=projected :: com.sbt.bm.ucp.common.model.dictionary.ConsentType :: field=None :: type_documentation_summary_substring :: doc='Тип согласия (на обработку персональных данных и т.д.)' :: inbound=True

## 87. Активные ограничения и блокировки
- 940 term='lock' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockInfo :: field=lockDate :: field_name_prefix :: doc='Дата резервирования клиента на редактирование' :: inbound=True
- 940 term='lock' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockResponse :: field=lockInfo :: field_name_prefix :: doc='Информация о блокировке карточки клиента' :: inbound=False
- 940 term='lock' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity :: field=lockDate :: field_name_prefix :: doc='Дата резервирования клиента на редактирование' :: inbound=False
- 940 term='lock' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity.Builder :: field=lockDate :: field_name_prefix :: doc=None :: inbound=False
- 930 term='lock' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockStatus :: field=None :: type_name_prefix :: doc=None :: inbound=True
- 910 term='огранич' scope=projected :: com.sbt.bm.ucp.smpr.RealEstate :: field=isRestrictive :: field_documentation_summary_prefix :: doc='Ограничения и обременения прав на объект' :: inbound=True
- 880 term='lock' scope=projected :: com.sbt.bm.ucp.retail.model.individual.Individual :: field=extraBlocks :: field_name_substring :: doc='Дополнительные атрибуты' :: inbound=True
- 830 term='блокиров' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockInfo :: field=deactivated :: field_documentation_summary_substring :: doc='Признак активности блокировки' :: inbound=True
- 830 term='блокиров' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.LockResponse :: field=lockInfo :: field_documentation_summary_substring :: doc='Информация о блокировке карточки клиента' :: inbound=False
- 830 term='блокиров' scope=all_declared_types :: com.sbt.bm.ucp.change_control.model.TwoManRuleEntity :: field=deactivated :: field_documentation_summary_substring :: doc='Признак активности блокировки' :: inbound=False

## 88. Ход текущего диалога (реплики, возражения, сигналы)

## 89. Эмоциональное состояние клиента в моменте

## 90. Время и контекст визита (ожидание в очереди, лимит времени)

## 91. Внешний сезонный/кампанийный контекст