<!-- markdownlint-disable-file MD024 -->
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Version [0.28.0](https://github.com/smithyhq/sqladmin/releases/tag/0.28.0): 2026-07-04

### Added

* feat: add `rich_text_fields` for pluggable rich text editors by @vahidzhe in [#1074](https://github.com/smithyhq/sqladmin/pull/1074)
* feat: pass `request` to column formatters by @Dexter2099 in [#1077](https://github.com/smithyhq/sqladmin/pull/1077)

### Changed

* build(deps): update Font Awesome to v7.2.0 by @CHC383 in [#1073](https://github.com/smithyhq/sqladmin/pull/1073)
* build(deps): update to jQuery v4.0.0 and Select2 v4.1.0 by @CHC383 in [#1070](https://github.com/smithyhq/sqladmin/pull/1070)
* build(deps): remove `tabler-icons.min.css.map` by @CHC383 in [#1071](https://github.com/smithyhq/sqladmin/pull/1071)

### Fixed

* fix: preserve base admin identity for polymorphic rows by @Dexter2099 in [#1076](https://github.com/smithyhq/sqladmin/pull/1076)
* fix: allow clearing nullable AJAX relation fields by @Dexter2099 in [#1075](https://github.com/smithyhq/sqladmin/pull/1075)
* fix: follow symlinks for static files by @Dexter2099 in [#1072](https://github.com/smithyhq/sqladmin/pull/1072)

### Upgrade notes

* **URL helpers:** `_build_url_for` and `_url_for_delete` use `self.identity` when the target object is an instance of the view's model (including polymorphic subclasses), and the object's class identity otherwise. Overrides of either helper apply to built-in templates.
* **Column formatters:** Existing two-argument formatters continue to work; pass a third `request` argument to opt in.
* **Front-end deps:** jQuery 4 and Select2 4.1 may affect custom admin JavaScript that relies on older APIs.

### New Contributors

* @Dexter2099 made their first contribution in [#1077](https://github.com/smithyhq/sqladmin/pull/1077)

**Full Changelog**: [0.27.2...0.28.0](https://github.com/smithyhq/sqladmin/compare/0.27.2...0.28.0)

## Version [0.27.2](https://github.com/smithyhq/sqladmin/releases/tag/0.27.2): 2026-06-08

### Changed

* build(deps): update to tabler v1.4.0, tabler-icons css v3.44.0 and migrate to Bootstrap v5 by @CHC383 in [#1058](https://github.com/smithyhq/sqladmin/pull/1058)

### Fixed

* fix: render column defaults on the create form by @dhcsousa in [#1061](https://github.com/smithyhq/sqladmin/pull/1061)
* fix(base-view): sidebar link falls back to /admin when @expose method is named index by @Vansh-Sharma27 in [#1062](https://github.com/smithyhq/sqladmin/pull/1062)
* Preserve list page after editing a record (#1055) by @Vansh-Sharma27 in [#1063](https://github.com/smithyhq/sqladmin/pull/1063)

### New Contributors

* @Vansh-Sharma27 made their first contribution in [#1062](https://github.com/smithyhq/sqladmin/pull/1062)

**Full Changelog**: [0.27.1...0.27.2](https://github.com/smithyhq/sqladmin/compare/0.27.1...0.27.2)

## Version [0.27.1](https://github.com/smithyhq/sqladmin/releases/tag/0.27.1): 2026-06-05

### Security

* Fix advisory `GHSA-ccg5-9c8w-xh6v`: restrict `ModelView.sort_query()` to the configured `column_sortable_list` allow-list (`self._sort_fields`) and reject invalid `sortBy` values with HTTP 400, preventing attacker-controlled ordering across arbitrary model and related-model columns and avoiding uncaught `AttributeError` (HTTP 500) by @aminalaee.

**Full Changelog**: [0.27.0...0.27.1](https://github.com/smithyhq/sqladmin/compare/0.27.0...0.27.1)

## Version [0.27.0](https://github.com/smithyhq/sqladmin/releases/tag/0.27.0): 2026-05-29

### Added

* feat: make admin logo width and height configurable (closes #1045) by @SAY-5 in [#1052](https://github.com/smithyhq/sqladmin/pull/1052)
* Feature: `after_model_change` response by @dhcsousa in [#1030](https://github.com/smithyhq/sqladmin/pull/1030)
* Create form_details_query by @MaximDementyev in [#1038](https://github.com/smithyhq/sqladmin/pull/1038)

### Fixed

* fix(list): fix the list view to limit the page width to viewport size by @CHC383 in [#1056](https://github.com/smithyhq/sqladmin/pull/1056)
* fix: forward kwargs to SessionMiddleware in AuthenticationBackend by @vahidzhe in [#1036](https://github.com/smithyhq/sqladmin/pull/1036)
* Fixed overriding form_args in forms.py and widgets.py by @mmzeynalli in [#1044](https://github.com/smithyhq/sqladmin/pull/1044)

### Docs

* Docs: add contributing page to documentation site by @vahidzhe in [#1034](https://github.com/smithyhq/sqladmin/pull/1034)

### New Contributors

* @CHC383 made their first contribution in [#1056](https://github.com/smithyhq/sqladmin/pull/1056)
* @SAY-5 made their first contribution in [#1052](https://github.com/smithyhq/sqladmin/pull/1052)
* @dhcsousa made their first contribution in [#1030](https://github.com/smithyhq/sqladmin/pull/1030)

**Full Changelog**: [0.26.0...0.27.0](https://github.com/smithyhq/sqladmin/compare/0.26.0...0.27.0)

## Version [0.26.0](https://github.com/smithyhq/sqladmin/releases/tag/0.26.0): 2025-05-16

### Fixed

* Drop Python 3.9 by @aminalaee in [#1047](https://github.com/smithyhq/sqladmin/pull/1047)
* Migrate to Zensical by @aminalaee in [#1048](https://github.com/smithyhq/sqladmin/pull/1048)

**Full Changelog**: [0.25.1...0.26.0](https://github.com/smithyhq/sqladmin/compare/0.25.1...0.26.0)

## Version [0.25.1](https://github.com/smithyhq/sqladmin/releases/tag/0.25.1): 2026-05-16

### Fixed

* fix: authenticate ajax lookup endpoint by @vahidzhe in [#1035](https://github.com/smithyhq/sqladmin/pull/1035)
* fix: Authorization bypass on `ajax_lookup`

### New Contributors

* @vahidzhe made their first contribution in [#1035](https://github.com/smithyhq/sqladmin/pull/1035)

**Full Changelog**: [0.25.0...0.25.1](https://github.com/smithyhq/sqladmin/compare/0.25.0...0.25.1)

## Version [0.25.0](https://github.com/smithyhq/sqladmin/releases/tag/0.25.0): 2026-04-18

### Added

* Move to org by @aminalaee in [#1018](https://github.com/smithyhq/sqladmin/pull/1018)
* extra blocks for templates allowing customization by @birddevelper in [#952](https://github.com/smithyhq/sqladmin/pull/952)
* Add template hooks to all filters for customizable UIs (dropdowns, sliders, etc.) by @fd-oncodna in [#970](https://github.com/smithyhq/sqladmin/pull/970)
* Support MappedAsDataclass by @Goradii in [#857](https://github.com/smithyhq/sqladmin/pull/857)
* save values types as is if possible while JSON export by @DenisDudnik in [#865](https://github.com/smithyhq/sqladmin/pull/865)
* Add toast to notify results for custom actions by @rusanpas in [#971](https://github.com/smithyhq/sqladmin/pull/971)
* Showing exceptions happened during delete in list page as per #898 by @mmzeynalli in [#1022](https://github.com/smithyhq/sqladmin/pull/1022)
* Quality of Life updates by @mmzeynalli in [#1026](https://github.com/smithyhq/sqladmin/pull/1026)
* [Feature] Check the available primary actions (edit, delete, view details) for each row on listing page. by @maxim-f1 in [#874](https://github.com/smithyhq/sqladmin/pull/874)

### Fixed

* Fix #841: Cannot update value of attribute with reserved name when it starts empty/null by @mmzeynalli in [#1028](https://github.com/smithyhq/sqladmin/pull/1028)
* Fix TypeError with UUID primary keys in issubclass check by @S3wnkin in [#992](https://github.com/smithyhq/sqladmin/pull/992)
* core: fix ambiguous column error when searching or sorting by @nurikk in [#983](https://github.com/smithyhq/sqladmin/pull/983)
* Handling SQLAlchemy UUID fields correctly by introducing new UuidField. by @mmzeynalli in [#1023](https://github.com/smithyhq/sqladmin/pull/1023)
* Fixes #915: Sorting exposed functions by their coded order not alphabetical by @mmzeynalli in [#1024](https://github.com/smithyhq/sqladmin/pull/1024)
* fix: add RootPathMiddleware for proper static file routing with root_… by @JartanFTW in [#996](https://github.com/smithyhq/sqladmin/pull/996)

### New Contributors

* @S3wnkin made their first contribution in [#992](https://github.com/smithyhq/sqladmin/pull/992)
* @fd-oncodna made their first contribution in [#970](https://github.com/smithyhq/sqladmin/pull/970)
* @Goradii made their first contribution in [#857](https://github.com/smithyhq/sqladmin/pull/857)
* @nurikk made their first contribution in [#983](https://github.com/smithyhq/sqladmin/pull/983)
* @DenisDudnik made their first contribution in [#865](https://github.com/smithyhq/sqladmin/pull/865)
* @rusanpas made their first contribution in [#971](https://github.com/smithyhq/sqladmin/pull/971)
* @JartanFTW made their first contribution in [#996](https://github.com/smithyhq/sqladmin/pull/996)

**Full Changelog**: [0.24.0...0.25.0](https://github.com/smithyhq/sqladmin/compare/0.24.0...0.25.0)

## Version [0.24.0](https://github.com/smithyhq/sqladmin/releases/tag/0.24.0): 2026-03-30

### Added

* Improve logout button and `logo_url` by @maxim-f1 in [#995](https://github.com/aminalaee/sqladmin/pull/995)
* Support filtering Date and Datetime fields with "less than" and "greater than" operations. by @caarmen in [#1010](https://github.com/aminalaee/sqladmin/pull/1010)
* Added switch style for checkbox and fixed related bug. by @maxim-f1 in [#975](https://github.com/aminalaee/sqladmin/pull/975)
* Add ModelView.search_auto_submit option for list search by @Airumian in [#1003](https://github.com/aminalaee/sqladmin/pull/1003)
* Add select_from to count query in models.py by @estyrke in [#969](https://github.com/aminalaee/sqladmin/pull/969)

### Fixed

* [Bug] Improved error display in the `delete` modal window by @maxim-f1 in [#994](https://github.com/aminalaee/sqladmin/pull/994)
* [Bug] Authorization vulnerability for expose and action by @maxim-f1 in [#993](https://github.com/aminalaee/sqladmin/pull/993)

### New Contributors

* @caarmen made their first contribution in [#1010](https://github.com/aminalaee/sqladmin/pull/1010)
* @Airumian made their first contribution in [#1003](https://github.com/aminalaee/sqladmin/pull/1003)
* @estyrke made their first contribution in [#969](https://github.com/aminalaee/sqladmin/pull/969)

**Full Changelog**: [0.23.0...0.24.0](https://github.com/aminalaee/sqladmin/compare/0.23.0...0.24.0)

## Version [0.23.0](https://github.com/smithyhq/sqladmin/releases/tag/0.23.0): 2026-02-04

### Added

* Highlight applied filters with background and clear option by @danmysak in [#964](https://github.com/aminalaee/sqladmin/pull/964)
* Implemented optional pretty CSV export by @TimofeiN in [#938](https://github.com/aminalaee/sqladmin/pull/938)

### Fixed

* fix: use children.extend in Menu.add by @wasinski in [#892](https://github.com/aminalaee/sqladmin/pull/892)
* fix: Support set-based relationships in list/detail views by @msukmanowsky in [#982](https://github.com/aminalaee/sqladmin/pull/982)
* Fixing an SQLAlchemy warning by @lorg in [#980](https://github.com/aminalaee/sqladmin/pull/980)
* Fix buttons width on details page by @MaximDementyev in [#978](https://github.com/aminalaee/sqladmin/pull/978)
* Migrate from hatchling to uv by @mmzeynalli in [#974](https://github.com/aminalaee/sqladmin/pull/974)
* Change PK column name to title in list/detail page by @wnowicki in [#977](https://github.com/aminalaee/sqladmin/pull/977)

### New Contributors

* @danmysak made their first contribution in [#964](https://github.com/aminalaee/sqladmin/pull/964)
* @TimofeiN made their first contribution in [#938](https://github.com/aminalaee/sqladmin/pull/938)
* @wasinski made their first contribution in [#892](https://github.com/aminalaee/sqladmin/pull/892)
* @msukmanowsky made their first contribution in [#982](https://github.com/aminalaee/sqladmin/pull/982)
* @MaximDementyev made their first contribution in [#978](https://github.com/aminalaee/sqladmin/pull/978)
* @mmzeynalli made their first contribution in [#974](https://github.com/aminalaee/sqladmin/pull/974)

**Full Changelog**: [0.22.0...0.23.0](https://github.com/aminalaee/sqladmin/compare/0.22.0...0.23.0)

## Version [0.22.0](https://github.com/smithyhq/sqladmin/releases/tag/0.22.0): 2025-11-24

### Added

* Implement OperationColumnFilter to filter String, Numeric, and UUID Types by @chezou in [#945](https://github.com/aminalaee/sqladmin/pull/945)
* Support Python 3.14 by @aminalaee in [#963](https://github.com/aminalaee/sqladmin/pull/963)

### Fixed

* Fix filters inccorect records count by @birddevelper in [#954](https://github.com/aminalaee/sqladmin/pull/954)
* docs - update the example ColumnFilter by @proby-actvo in [#949](https://github.com/aminalaee/sqladmin/pull/949)
* Documentation improvements by @wnowicki in [#941](https://github.com/aminalaee/sqladmin/pull/941)
* Fix date and time type handling when used as primary key by @twoodwark in [#958](https://github.com/aminalaee/sqladmin/pull/958)

**Full Changelog**: [0.21.0...0.22.0](https://github.com/aminalaee/sqladmin/compare/0.21.0...0.22.0)

## Version [0.21.0](https://github.com/smithyhq/sqladmin/releases/tag/0.21.0): 2025-07-02

### Added

* Add `category_icon` by @sheldygg in [#848](https://github.com/aminalaee/sqladmin/pull/848)
* Add model convertors docs by @Vasiliy566 in [#883](https://github.com/aminalaee/sqladmin/pull/883)
* Allow custom response in authentication logout by @joschnitzbauer in [#914](https://github.com/aminalaee/sqladmin/pull/914)
* ModelView @expose decorator support by @foarsitter in [#881](https://github.com/aminalaee/sqladmin/pull/881)
* Adding the ability to add filters to model views by @lorg in [#906](https://github.com/aminalaee/sqladmin/pull/906)
* Details page query by @wray27 in [#929](https://github.com/aminalaee/sqladmin/pull/929)
* export csv/json in `utf-8` by @alserious in [#911](https://github.com/aminalaee/sqladmin/pull/911)
* Indicate Required Fields with a Red Asterisk by @maxim-f1 in [#880](https://github.com/aminalaee/sqladmin/pull/880)

### Fixed

* Update hatch command in CONTRIBUTING.md by @foarsitter in [#882](https://github.com/aminalaee/sqladmin/pull/882)
* fix: CategoryMenu is_active logic by @retromechs in [#920](https://github.com/aminalaee/sqladmin/pull/920)
* Doc update - Related model name by @wnowicki in [#917](https://github.com/aminalaee/sqladmin/pull/917)
* docs: Added model context, fixed syntax by @sreyemnayr in [#930](https://github.com/aminalaee/sqladmin/pull/930)

**Full Changelog**: [0.20.1...0.21.0](https://github.com/aminalaee/sqladmin/compare/0.20.1...0.21.0)

## Version [0.20.1](https://github.com/smithyhq/sqladmin/releases/tag/0.20.1): 2024-10-28

### Fixed

* Fix export json related model by @Vasiliy566 in [#837](https://github.com/aminalaee/sqladmin/pull/837)
* Fix JSON export trailing comma by @jbrendel in [#843](https://github.com/aminalaee/sqladmin/pull/843)

**Full Changelog**: [0.20.0...0.20.1](https://github.com/aminalaee/sqladmin/compare/0.20.0...0.20.1)

## Version [0.20.0](https://github.com/smithyhq/sqladmin/releases/tag/0.20.0): 2024-10-17

### Added

* add json export format. by @Vasiliy566 in [#829](https://github.com/aminalaee/sqladmin/pull/829)

### Fixed

* clamp page if it exceeds the maximum page by @alex-lambdaloopers in [#814](https://github.com/aminalaee/sqladmin/pull/814)

### New Contributors

* @Vasiliy566 made their first contribution in [#829](https://github.com/aminalaee/sqladmin/pull/829)

**Full Changelog**: [0.19.0...0.20.0](https://github.com/aminalaee/sqladmin/compare/0.19.0...0.20.0)

## Version [0.19.0](https://github.com/smithyhq/sqladmin/releases/tag/0.19.0): 2024-09-06

### Added

* Add favicon by @sheldygg in [#787](https://github.com/aminalaee/sqladmin/pull/787)
* Add tabler icons by @r-m-n in [#795](https://github.com/aminalaee/sqladmin/pull/795)
* feat: use favicon_url instead of logo_url for favicon by @alex-lambdaloopers in [#800](https://github.com/aminalaee/sqladmin/pull/800)
* Allow multiple ajax sorts and changes to result size by @mfriedy in [#805](https://github.com/aminalaee/sqladmin/pull/805)

### Fixed

* Fix column_property by @aminalaee in [#791](https://github.com/aminalaee/sqladmin/pull/791)
* Fix page number issue when changing page size by @numberbee7070 in [#782](https://github.com/aminalaee/sqladmin/pull/782)
* Document update to resolve DeprecationWarning from Starlette (#809) by @a4rcvv in [#810](https://github.com/aminalaee/sqladmin/pull/810)
* Bug fix: unhandled exception during AjaxSelect load by @diskream in [#727](https://github.com/aminalaee/sqladmin/pull/727)

**Full Changelog**: [0.18.0...0.19.0](https://github.com/aminalaee/sqladmin/compare/0.18.0...0.19.0)

## Version [0.18.0](https://github.com/smithyhq/sqladmin/releases/tag/0.18.0): 2024-07-01

### Added

* Add `form_rules`, `form_create_rules`, `form_edit_rules` by @aminalaee in [#779](https://github.com/aminalaee/sqladmin/pull/779)
* Add more docs for overriding default tempates by @jonocodes in [#769](https://github.com/aminalaee/sqladmin/pull/769)

### Fixed

* Fix edit_form_query documentation example by @lukeclimen in [#777](https://github.com/aminalaee/sqladmin/pull/777)

**Full Changelog**: [0.17.0...0.18.0](https://github.com/aminalaee/sqladmin/compare/0.17.0...0.18.0)

## Version [0.17.0](https://github.com/smithyhq/sqladmin/releases/tag/0.17.0): 2024-05-13

### Added

* Add field description to Create/Edit templates by @ngaranko in [#722](https://github.com/aminalaee/sqladmin/pull/722)
* Add edit_form_query method by @lukeclimen in [#745](https://github.com/aminalaee/sqladmin/pull/745)
* Validate page and pageSize query parameters by @BhuwanPandey in [#752](https://github.com/aminalaee/sqladmin/pull/752)

### Fixed

* Hide save and add another button from edit.html if can_create is False by @MaximZemskov in [#742](https://github.com/aminalaee/sqladmin/pull/742)
* Fix list page sort symbol by @aminalaee in [#744](https://github.com/aminalaee/sqladmin/pull/744)
* Move template files from `templates` to `templates/sqladmin` by @hasansezertasan in [#748](https://github.com/aminalaee/sqladmin/pull/748)
* Fix `form_args` default by @aminalaee in [#756](https://github.com/aminalaee/sqladmin/pull/756)
* Fix getting column python type by @aminalaee in [#757](https://github.com/aminalaee/sqladmin/pull/757)
* Fix File and Image fields checkbox and input by @aminalaee in [#761](https://github.com/aminalaee/sqladmin/pull/761)
* Switch relationship loading to selectionload by @aminalaee in [#758](https://github.com/aminalaee/sqladmin/pull/758)
* Fix DELETE call query params by @aminalaee in [#763](https://github.com/aminalaee/sqladmin/pull/763)

**Full Changelog**: [0.16.1...0.17.0](https://github.com/aminalaee/sqladmin/compare/0.16.1...0.17.0)

## Version [0.16.1](https://github.com/smithyhq/sqladmin/releases/tag/0.16.1): 2024-02-20

### Fixed

* Re-add http_exception handler to Admin class in [#694](https://github.com/aminalaee/sqladmin/pull/694)
* Move non-field-specific errors to top of edit and create forms in [#707](https://github.com/aminalaee/sqladmin/pull/707)
* Fix sort by model attribute in [#713](https://github.com/aminalaee/sqladmin/pull/713)
* Fix Category not respecting is_visible and is_accessible in [#698](https://github.com/aminalaee/sqladmin/pull/698)

**Full Changelog**: [0.16.0...0.16.1](https://github.com/aminalaee/sqladmin/compare/0.16.0...0.16.1)

## Version [0.16.0](https://github.com/smithyhq/sqladmin/releases/tag/0.16.0): 2023-11-14

### Added

* Switch to async templates by @aminalaee in [#652](https://github.com/aminalaee/sqladmin/pull/652)
* Allow using related model fields in list/details page by @aminalaee in [#653](https://github.com/aminalaee/sqladmin/pull/653)
* Allow sort by related model field by @aminalaee in [#654](https://github.com/aminalaee/sqladmin/pull/654)
* Add search by related model field by @aminalaee in [#655](https://github.com/aminalaee/sqladmin/pull/655)
* Expose request to model events by @holdmybeer1min in [#660](https://github.com/aminalaee/sqladmin/pull/660)

### Fixed

* Allow model columns to bear the same name as reserved wtforms.BaseForm attributes by @brouberol in [#658](https://github.com/aminalaee/sqladmin/pull/658)
* Change pk converter in routes by @aminalaee in [#666](https://github.com/aminalaee/sqladmin/pull/666)
* Fix multiple PK model containing boolean values by @ncarvajalc in [#670](https://github.com/aminalaee/sqladmin/pull/670)
* Fix brand icon is not showing by @WiraDKP in [#665](https://github.com/aminalaee/sqladmin/pull/665)

**Full Changelog**: [0.15.2...0.16.0](https://github.com/aminalaee/sqladmin/compare/0.15.2...0.16.0)

## Version [0.15.1](https://github.com/smithyhq/sqladmin/releases/tag/0.15.1): 2023-10-02

### Fixed

* Avoid populating Select2 input with existing option by @Toshakins in [#626](https://github.com/aminalaee/sqladmin/pull/626)
* Fix ItemMenu sort issue by @aminalaee in [#631](https://github.com/aminalaee/sqladmin/pull/631)

### Added

* Add customized sort query signature (#624) by @YarLikviD in [#625](https://github.com/aminalaee/sqladmin/pull/625)

**Full Changelog**: [0.15.0...0.15.1](https://github.com/aminalaee/sqladmin/compare/0.15.0...0.15.1)

## Version [0.15.0](https://github.com/smithyhq/sqladmin/releases/tag/0.15.0): 2023-09-19

### Breaking Changes

* Update AuthenticationBackend signature by @aminalaee in [#581](https://github.com/aminalaee/sqladmin/pull/581)
* Change signature of `list_query` and `count_query` by @aminalaee in [#610](https://github.com/aminalaee/sqladmin/pull/610)

### Added

* Search in list when typing by @anton-petrov in [#592](https://github.com/aminalaee/sqladmin/pull/592)
* Add `category` config by @aminalaee in [#616](https://github.com/aminalaee/sqladmin/pull/616)
* Switch to HTML time input for Time field by @aminalaee in [#595](https://github.com/aminalaee/sqladmin/pull/595)
* Add modal confirmation for bulk delete by @aminalaee in [#612](https://github.com/aminalaee/sqladmin/pull/612)

### Fixed

* Fix 'itsdangerous' import error when not using Authentication Backend by @GriceTurrble in [#597](https://github.com/aminalaee/sqladmin/pull/597)
* Fix docs: Cookbook, Using a request object by @s1beria21 in [#575](https://github.com/aminalaee/sqladmin/pull/575)
* Fix delete error no rows selected by @aminalaee in [#591](https://github.com/aminalaee/sqladmin/pull/591)
* Fix typing of Admin session_maker by @sheldygg in [#604](https://github.com/aminalaee/sqladmin/pull/604)
* Fix broken link in doc by @YannickLeRoux in [#620](https://github.com/aminalaee/sqladmin/pull/620)

**Full Changelog**: [0.14.1...0.15.0](https://github.com/aminalaee/sqladmin/compare/0.14.1...0.15.0)

## Version [0.14.1](https://github.com/smithyhq/sqladmin/releases/tag/0.14.1): 2023-08-08

### Fixed

* Fix Detail page to not use label to get value in [#570](https://github.com/aminalaee/sqladmin/pull/570)

**Full Changelog**: [0.14.0...0.14.1](https://github.com/aminalaee/sqladmin/compare/0.14.0...0.14.1)

## Version [0.14.0](https://github.com/smithyhq/sqladmin/releases/tag/0.14.0): 2023-08-02

### Added

* Pass request to model view methods by @rossmacarthur in [#547](https://github.com/aminalaee/sqladmin/pull/547)
* Set `sessionmaker` on `BaseAdmin` by @rossmacarthur in [#542](https://github.com/aminalaee/sqladmin/pull/542)
* Allow custom properties by @aminalaee in [#544](https://github.com/aminalaee/sqladmin/pull/544)
* Change signature of delete_model by @aminalaee in [#550](https://github.com/aminalaee/sqladmin/pull/550)
* Support SQLAlchemy sessionmaker in Admin by @aminalaee in [#565](https://github.com/aminalaee/sqladmin/pull/565)

### Fixed

* Fix `expose` and `action` Auth backend not called by @aminalaee in [#561](https://github.com/aminalaee/sqladmin/pull/561)

**Full Changelog**: [0.13.0...0.14.0](https://github.com/aminalaee/sqladmin/compare/0.13.0...0.14.0)

## Version [0.13.0](https://github.com/smithyhq/sqladmin/releases/tag/0.13.0): 2023-06-30

### Fixed

* Remove httpx from requirements by @agn-7 in [#520](https://github.com/aminalaee/sqladmin/pull/520)
* Fix issue when search query contains special characters by @uriyyo in [#523](https://github.com/aminalaee/sqladmin/pull/523)
* Fix Ajax UUID by @aminalaee in [#525](https://github.com/aminalaee/sqladmin/pull/525)
* Fix search pagination by @aminalaee in [#528](https://github.com/aminalaee/sqladmin/pull/528)
* Drop Python3.7 by @aminalaee in [#530](https://github.com/aminalaee/sqladmin/pull/530)
* Fix Enum in detail page by @aminalaee in [#531](https://github.com/aminalaee/sqladmin/pull/531)
* Add `unique()` to query related models by @florianabel in [#535](https://github.com/aminalaee/sqladmin/pull/535)
* Add PosrgreSQL JSONB type support by @uriyyo in [#533](https://github.com/aminalaee/sqladmin/pull/533)

**Full Changelog**: [0.12.0...0.13.0](https://github.com/aminalaee/sqladmin/compare/0.12.0...0.13.0)

## Version [0.12.0](https://github.com/smithyhq/sqladmin/releases/tag/0.12.0): 2023-06-13

### Added

* Support `sqlalchemy.sql.sqltypes.Uuid` by @dexter-dopping-ekco in [#501](https://github.com/aminalaee/sqladmin/pull/501)
* Implement multi pk support by @dexter-dopping-ekco in [#507](https://github.com/aminalaee/sqladmin/pull/507)
* Support special `__all__` keyword by @aminalaee in [#511](https://github.com/aminalaee/sqladmin/pull/511)
* use @login_required for custom actions and views by @aminalaee in [#513](https://github.com/aminalaee/sqladmin/pull/513)

### Fixed

* Each `ModelView` can now have actions with the same name/slug by @murrple-1 in [#503](https://github.com/aminalaee/sqladmin/pull/503)
* Fix count query in search page by @aminalaee in [#506](https://github.com/aminalaee/sqladmin/pull/506)

**Full Changelog**: [0.11.0...0.12.0](https://github.com/aminalaee/sqladmin/compare/0.11.0...0.12.0)

## Version [0.11.0](https://github.com/smithyhq/sqladmin/releases/tag/0.11.0): 2023-05-23

### Added

* Add ability to specify custom actions by @murrple-1 in [#486](https://github.com/aminalaee/sqladmin/pull/486)
* Add `ChoiceType` by @aminalaee in [#482](https://github.com/aminalaee/sqladmin/pull/482)
* Add sqlalchemy_fields URLType converter by @aminalaee in [#493](https://github.com/aminalaee/sqladmin/pull/493)
* Upgrade fontawesome by @aminalaee in [#481](https://github.com/aminalaee/sqladmin/pull/481)

**Full Changelog**: [0.10.3...0.11.0](https://github.com/aminalaee/sqladmin/compare/0.10.3...0.11.0)

## Version [0.10.3](https://github.com/smithyhq/sqladmin/releases/tag/0.10.3): 2023-04-21

### Fixed

* Fix ImageType converter by @aminalaee in [#471](https://github.com/aminalaee/sqladmin/pull/471)
* reset UploadFile seek after reading by @murrple-1 in [#473](https://github.com/aminalaee/sqladmin/pull/473)
* Fix unnecessary joins in details and edit page by @aminalaee in [#476](https://github.com/aminalaee/sqladmin/pull/476)

**Full Changelog**: [0.10.2...0.10.3](https://github.com/aminalaee/sqladmin/compare/0.10.2...0.10.3)

## Version [0.10.2](https://github.com/smithyhq/sqladmin/releases/tag/0.10.2): 2023-04-15

### Fixed

* Fix nullable string fields by @aminalaee in [#465](https://github.com/aminalaee/sqladmin/pull/465)
* Fix Multiselect field saving only one value by @nik-joseph in [#463](https://github.com/aminalaee/sqladmin/pull/463)

**Full Changelog**: [0.10.1...0.10.2](https://github.com/aminalaee/sqladmin/compare/0.10.1...0.10.2)

## Version [0.10.1](https://github.com/smithyhq/sqladmin/releases/tag/0.10.1): 2023-03-25

### Fixed

* Fix PK getters for related objects by @timoniq in [#449](https://github.com/aminalaee/sqladmin/pull/449)

**Full Changelog**: [0.10.0...0.10.1](https://github.com/aminalaee/sqladmin/compare/0.10.0...0.10.1)

## Version [0.10.0](https://github.com/smithyhq/sqladmin/releases/tag/0.10.0): 2023-03-15

### Breaking change

* Change AuthenticationBackend `authenticate` signature to support OAuth in [#440](https://github.com/aminalaee/sqladmin/pull/440)

### Added

* Add File field in [#424](https://github.com/aminalaee/sqladmin/pull/424)
* Support SQLALchemy Interval type in [#438](https://github.com/aminalaee/sqladmin/pull/438)

### Fixed

* Fix docstrings by @linomp in [#434](https://github.com/aminalaee/sqladmin/pull/434)
* Update to work with Starlette URL type in url_for by @aminalaee in [#444](https://github.com/aminalaee/sqladmin/pull/444)
* Fix nullable Integers to accept zero value by @ovginkel in [#445](https://github.com/aminalaee/sqladmin/pull/445)

**Full Changelog**: [0.9.0...0.10.0](https://github.com/aminalaee/sqladmin/compare/0.9.0...0.10.0)

## Version [0.9.0](https://github.com/smithyhq/sqladmin/releases/tag/0.9.0): 2023-02-07

### Added

* Support SQLAlchemy v2 in [#411](https://github.com/aminalaee/sqladmin/pull/411)
* Support PostgreSQL arrays in [#414](https://github.com/aminalaee/sqladmin/pull/414)
* Add custom form converters in [#399](https://github.com/aminalaee/sqladmin/pull/399)
* Support SQLAlchemy composite types in [#421](https://github.com/aminalaee/sqladmin/pull/421)
* Add sqlalchemy_utils `PhoneNumberType`, `ColorType` and `ArrowType` in [#422](https://github.com/aminalaee/sqladmin/pull/422)

### Fixed

* Fix re-rendering create/edit page with existing data in [#385](https://github.com/aminalaee/sqladmin/pull/385)
* Fix exclude columns breaking order in [#407](https://github.com/aminalaee/sqladmin/pull/407)
* Fix control relationships in list page in [#409](https://github.com/aminalaee/sqladmin/pull/409)
* Fix asyncpg BigInt query in [#416](https://github.com/aminalaee/sqladmin/pull/416)

**Full Changelog**: [0.8.0...0.9.0](https://github.com/aminalaee/sqladmin/compare/0.8.0...0.9.0)

## Version [0.8.0](https://github.com/smithyhq/sqladmin/releases/tag/0.8.0): 2022-11-22

### Added

* Add `save_as` option by @aminalaee in [#377](https://github.com/aminalaee/sqladmin/pull/377)
* Add `save_as_continue` option by @aminalaee in [#379](https://github.com/aminalaee/sqladmin/pull/379)
* Add extra Save buttons for Create/Edit page by @aminalaee in [#373](https://github.com/aminalaee/sqladmin/pull/373)
* Display errors in alert for create/edit page by @aminalaee in [#382](https://github.com/aminalaee/sqladmin/pull/382)

### Fixed

* Fix `_url_for` methods ignoring root_path by @aminalaee in [#371](https://github.com/aminalaee/sqladmin/pull/371)
* Fix export to use `list_query` option by @villqrd in [#381](https://github.com/aminalaee/sqladmin/pull/381)

**Full Changelog**: [0.7.0...0.8.0](https://github.com/aminalaee/sqladmin/compare/0.7.0...0.8.0)

## Version [0.7.0](https://github.com/smithyhq/sqladmin/releases/tag/0.7.0): 2022-11-03

### Added

* Add `on_model_change` and `after_model_change` methods by @dima23113 in [#342](https://github.com/aminalaee/sqladmin/pull/342)
* Add `on_model_delete` and `after_model_delete` methods by @aminalaee in [#343](https://github.com/aminalaee/sqladmin/pull/343)

### Fixed

* Fix search by uuid column by @aminalaee in [#366](https://github.com/aminalaee/sqladmin/pull/366)
* Update tests after starlette upgrade by @aminalaee in [#344](https://github.com/aminalaee/sqladmin/pull/344)
* Remove hard-coded related model limit by @aminalaee in [#354](https://github.com/aminalaee/sqladmin/pull/354)
* Improve items list UI by @ischaojie in [#349](https://github.com/aminalaee/sqladmin/pull/349)
* Make navbar work on small screens by @aminalaee in [#362](https://github.com/aminalaee/sqladmin/pull/362)

### Internal

* Add mypy check with config no_implicit_optional by @ischaojie in [#360](https://github.com/aminalaee/sqladmin/pull/360)
* Support test-suite py311 by @ischaojie in [#365](https://github.com/aminalaee/sqladmin/pull/365)
* Add py.typed for the package to ship its typing information by @franciscorode in [#346](https://github.com/aminalaee/sqladmin/pull/346)

**Full Changelog**: [0.6.1...0.7.0](https://github.com/aminalaee/sqladmin/compare/0.6.1...0.7.0)

## Version [0.6.1](https://github.com/smithyhq/sqladmin/releases/tag/0.6.1): 2022-09-25

### Fixed

* Fix Boolean field for both nullable and non-nullable cases in [#336](https://github.com/aminalaee/sqladmin/pull/336)
* Fix Flatpickr not respecting readonly inputs in [#336](https://github.com/aminalaee/sqladmin/pull/336)
* Disable batch delete when can_delete permission is not provided in [#335](https://github.com/aminalaee/sqladmin/pull/335)

**Full Changelog**: [0.6.0...0.6.1](https://github.com/aminalaee/sqladmin/compare/0.6.0...0.6.1)

## Version [0.6.0](https://github.com/smithyhq/sqladmin/releases/tag/0.6.0): 2022-09-19

### Added

* Add bulk delete action by @aminalaee in [#317](https://github.com/aminalaee/sqladmin/pull/317)

### Fixed

* Handle null values when column is nullable by @aminalaee in [#323](https://github.com/aminalaee/sqladmin/pull/323)
* Switch Boolean field to select field by @aminalaee in [#321](https://github.com/aminalaee/sqladmin/pull/321)

### Internal

* Fix form_ajax_refs example in documentation by @GitBib in [#311](https://github.com/aminalaee/sqladmin/pull/311)
* Remove watch in mkdocstrings mkdocs's config by @ischaojie in [#306](https://github.com/aminalaee/sqladmin/pull/306)

**Full Changelog**: [0.5.0...0.6.0](https://github.com/aminalaee/sqladmin/compare/0.5.0...0.6.0)

## Version [0.5.0](https://github.com/smithyhq/sqladmin/releases/tag/0.5.0): 2022-09-06

### Added

* Add `remote_ajax_refs` in [#292](https://github.com/aminalaee/sqladmin/pull/292)

### Internal

* Avoid select query with ajax_form_refs in [#300](https://github.com/aminalaee/sqladmin/pull/300)
* Add docs for form_ajax_refs in [#302](https://github.com/aminalaee/sqladmin/pull/302)

**Full Changelog**: [0.4.0...0.5.0](https://github.com/aminalaee/sqladmin/compare/0.4.0...0.5.0)

## Version [0.4.0](https://github.com/smithyhq/sqladmin/releases/tag/0.4.0): 2022-08-31

### Added

* Add Date and DateTime pickers using Fatpickr in [#288](https://github.com/aminalaee/sqladmin/pull/288)
* Add Time picker using Flatpickr in [#294](https://github.com/aminalaee/sqladmin/pull/294)

### Internal

* Remove MomentJS in [#289](https://github.com/aminalaee/sqladmin/pull/289)
* Remove Select2 widgets in [#293](https://github.com/aminalaee/sqladmin/pull/293)

**Full Changelog**: [0.3.0...0.4.0](https://github.com/aminalaee/sqladmin/compare/0.3.0...0.4.0)

## Version [0.3.0](https://github.com/smithyhq/sqladmin/releases/tag/0.3.0): 2022-08-26

### Added

* Add `AuthenticationBackend` in [#277](https://github.com/aminalaee/sqladmin/pull/277)
* Update Authentication docs in [#278](https://github.com/aminalaee/sqladmin/pull/278)

**Full Changelog**: [0.2.1...0.3.0](https://github.com/aminalaee/sqladmin/compare/0.2.1...0.3.0)

## Version [0.2.1](https://github.com/smithyhq/sqladmin/releases/tag/0.2.1): 2022-08-04

### Fixed

* Fix `middlewares` and `ENGINE_TYPE` types in [#266](https://github.com/aminalaee/sqladmin/pull/266)
* Fix middlewares not being applied in [#267](https://github.com/aminalaee/sqladmin/pull/267) and [#271](https://github.com/aminalaee/sqladmin/pull/271)

**Full Changelog**: [0.2.0...0.2.1](https://github.com/aminalaee/sqladmin/compare/0.2.0...0.2.1)

## Version [0.2.0](https://github.com/smithyhq/sqladmin/releases/tag/0.2.0): 2022-08-01

### Added

* Add `list_query`, `count_query` and `search_query` options in [#243](https://github.com/aminalaee/sqladmin/pull/243)
* Add `BaseView` for custom pages in [#244](https://github.com/aminalaee/sqladmin/pull/244)
* Add `expose` for BaseView in [#251](https://github.com/aminalaee/sqladmin/pull/251)
* Rename `ModelAdmin` to `ModelView` in [#249](https://github.com/aminalaee/sqladmin/pull/249)

**Full Changelog**: [0.1.12...0.2.0](https://github.com/aminalaee/sqladmin/compare/0.1.12...0.2.0)

## Version [0.1.12](https://github.com/smithyhq/sqladmin/releases/tag/0.1.12): 2022-07-13

### Added

* Add time field converter by @ischaojie in [#214](https://github.com/aminalaee/sqladmin/pull/214)
* Add Edit button for "Details" page by @cuamckuu in [#222](https://github.com/aminalaee/sqladmin/pull/222)
* Add column_type_formatters by @aminalaee in [#239](https://github.com/aminalaee/sqladmin/pull/239)

### Fixed

* Fix lazy subuqery in list query by @aminalaee in [#212](https://github.com/aminalaee/sqladmin/pull/212)
* Fix missing browser tab title by @cuamckuu in [#229](https://github.com/aminalaee/sqladmin/pull/229)
* Remove sourceMappingURL in JS files by @aminalaee in [#231](https://github.com/aminalaee/sqladmin/pull/231)

**Full Changelog**: [0.1.11...0.1.12](https://github.com/aminalaee/sqladmin/compare/0.1.11...0.1.12)

## Version [0.1.11](https://github.com/smithyhq/sqladmin/releases/tag/0.1.11): 2022-06-23

### Added

* Add `form_include_pk` option by @aminalaee in [#207](https://github.com/aminalaee/sqladmin/pull/207)

### Fixed

* Fix handling of iterable fields by @okapies in [#204](https://github.com/aminalaee/sqladmin/pull/204)
* Fix nullable Enum form by @aminalaee in [#205](https://github.com/aminalaee/sqladmin/pull/205)

**Full Changelog**: [0.1.10...0.1.11](https://github.com/aminalaee/sqladmin/compare/0.1.10...0.1.11)

## Version [0.1.10](https://github.com/smithyhq/sqladmin/releases/tag/0.1.10): 2022-06-21

### Added

* Add support for one-to-one relationship by @okapies in [#182](https://github.com/aminalaee/sqladmin/pull/182)
* Add support for UUIDType from sqlalchemy_utils by @okapies in [#183](https://github.com/aminalaee/sqladmin/pull/183)
* Add sqlalchemy_utils URL, Currency and  Timezone by @aminalaee in [#185](https://github.com/aminalaee/sqladmin/pull/185)
* Add form_widget_args by @aminalaee in [#188](https://github.com/aminalaee/sqladmin/pull/188)
* Add column_default_sort by @aminalaee in [#191](https://github.com/aminalaee/sqladmin/pull/191)

### Fixed

* Fix link relationship to details page when null by @aminalaee in [#174](https://github.com/aminalaee/sqladmin/pull/174)
* docs: fix typos by @pgrimaud in [#161](https://github.com/aminalaee/sqladmin/pull/161)
* Allow QuerySelectField override object_list with form_args by @aminalaee in [#171](https://github.com/aminalaee/sqladmin/pull/171)
* Fix form fields order when specifying columns by @okapies in [#184](https://github.com/aminalaee/sqladmin/pull/184)
* Fix ModelConverter when `impl` is not callable by @aminalaee in [#186](https://github.com/aminalaee/sqladmin/pull/186)

**Full Changelog**: [0.1.9...0.1.10](https://github.com/aminalaee/sqladmin/compare/0.1.9...0.1.10)

## Version [0.1.9](https://github.com/smithyhq/sqladmin/releases/tag/0.1.9): 2022-05-27

### Added

* Add column_formatters by @skarrok in [#140](https://github.com/aminalaee/sqladmin/pull/140)
* Add column_formatters_detail by @aminalaee in [#141](https://github.com/aminalaee/sqladmin/pull/141)
* Handling for sqlalchemy_utils EmailType and IPAddressType by @colin99d in [#150](https://github.com/aminalaee/sqladmin/pull/150)
* Link relationships to detail page by @aminalaee in [#153](https://github.com/aminalaee/sqladmin/pull/153)

### Fixed

* Function signature typing, and renames by @dwreeves in [#116](https://github.com/aminalaee/sqladmin/pull/116)
* Fix SQLModel UUID type by @aminalaee in [#158](https://github.com/aminalaee/sqladmin/pull/158)

**Full Changelog**: [0.1.8...0.1.9](https://github.com/aminalaee/sqladmin/compare/0.1.8...0.1.9)

## Version [0.1.8](https://github.com/smithyhq/sqladmin/releases/tag/0.1.8): 2022-04-19

### Added

* Add csv export support by @dwreeves in [#101](https://github.com/aminalaee/sqladmin/pull/101)
* Expose Starlette middlewares and debug to the Admin by @tr11 in [#114](https://github.com/aminalaee/sqladmin/pull/114)

### Fixed

* Fix Export unlimited rows by @aminalaee in [#107](https://github.com/aminalaee/sqladmin/pull/107)
* Add form and export options docs by @aminalaee in [#110](https://github.com/aminalaee/sqladmin/pull/110)
* fix docstring issues by adding an explicit handler by @dwreeves in [#106](https://github.com/aminalaee/sqladmin/pull/106)
* Fix get_model_attr with column labels by @aminalaee in [#128](https://github.com/aminalaee/sqladmin/pull/128)
* Delay call to `self.get_converter` to use `form_overrides` by @lovetoburnswhen in [#129](https://github.com/aminalaee/sqladmin/pull/129)

**Full Changelog**: [0.1.7...0.1.8](https://github.com/aminalaee/sqladmin/compare/0.1.7...0.1.8)

## Version [0.1.7](https://github.com/smithyhq/sqladmin/releases/tag/0.1.7): 2022-03-22

### Added

* Add SQLModel support by @aminalaee in [#94](https://github.com/aminalaee/sqladmin/pull/94)
* Add form-specific functionality to ModelAdmin by @dwreeves in [#97](https://github.com/aminalaee/sqladmin/pull/97)
* Add `UUID` field converter by @aminalaee in [#82](https://github.com/aminalaee/sqladmin/pull/82)
* Add PostgreSQL `INET` and `MACADDR` converters by @aminalaee in [#83](https://github.com/aminalaee/sqladmin/pull/83)

### Fixed

* Fix Boolean field checkbox UI by @aminalaee in [#88](https://github.com/aminalaee/sqladmin/pull/88)
* Fix PostgreSQL UUID PrimaryKey by @aminalaee in [#92](https://github.com/aminalaee/sqladmin/pull/92)
* Fix Source Code Link by @baurt in [#95](https://github.com/aminalaee/sqladmin/pull/95)

**Full Changelog**: [0.1.6...0.1.7](https://github.com/aminalaee/sqladmin/compare/0.1.6...0.1.7)

## Version [0.1.6](https://github.com/smithyhq/sqladmin/releases/tag/0.1.6): 2022-03-09

### Added

* FontAwesome6 icons in [#78](https://github.com/aminalaee/sqladmin/pull/78)
* Add `column_sortable_list` in [#65](https://github.com/aminalaee/sqladmin/pull/65)
* Add JSON column converters in [#74](https://github.com/aminalaee/sqladmin/pull/74)

### Fixed

* Fix URL search regex in [#67](https://github.com/aminalaee/sqladmin/pull/67)
* Fix Enum in Edit page in [#71](https://github.com/aminalaee/sqladmin/pull/71)

**Full Changelog**: [0.1.5...0.1.6](https://github.com/aminalaee/sqladmin/compare/0.1.5...0.1.6)

## Version [0.1.5](https://github.com/smithyhq/sqladmin/releases/tag/0.1.5): 2022-02-24

### Added

* Authentication in [#37](https://github.com/aminalaee/sqladmin/pull/37)
* Add Edit view page in [#60](https://github.com/aminalaee/sqladmin/pull/60)
* Add `column_searchable_list` in [#61](https://github.com/aminalaee/sqladmin/pull/61)

### Internal

* Cleanup DB queries in [#51](https://github.com/aminalaee/sqladmin/pull/54)

**Full Changelog**: [0.1.4...0.1.5](https://github.com/aminalaee/sqladmin/compare/0.1.4...0.1.5)

## Version [0.1.4](https://github.com/smithyhq/sqladmin/releases/tag/0.1.4): 2022-02-16

### Added

* Allow templates to be configured in [#52](https://github.com/aminalaee/sqladmin/pull/52)
* Add page size option links in [#34](https://github.com/aminalaee/sqladmin/pull/34)

### Fixed

* Improve pagination in [#36](https://github.com/aminalaee/sqladmin/pull/36)

### Internal

* Instantiate ModelAdmin internally to avoid class methods in [#31](https://github.com/aminalaee/sqladmin/pull/31)

**Full Changelog**: [0.1.3...0.1.4](https://github.com/aminalaee/sqladmin/compare/0.1.3...0.1.4)

## Version [0.1.3](https://github.com/smithyhq/sqladmin/releases/tag/0.1.3): 2022-01-24

### Added

* Add `title` and `logo` options in [#20](https://github.com/aminalaee/sqladmin/pull/20)
* Adding `order_by` to list pagination query in [#25](https://github.com/aminalaee/sqladmin/pull/25)
* Allow Relationship properties in list and detail views in [#22](https://github.com/aminalaee/sqladmin/pull/22)

**Full Changelog**: [0.1.2...0.1.3](https://github.com/aminalaee/sqladmin/compare/0.1.2...0.1.3)
