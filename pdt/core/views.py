"""PDT core views."""
import collections
import functools
import logging
import pprint

from django.contrib.auth.decorators import login_required
from django.template.loader import render_to_string
from django.template import RequestContext
from django.core.urlresolvers import reverse
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import get_object_or_404, render

from constance import config

from .models import (
    Release,
    CaseCategory,
)

logger = logging.getLogger(__name__)

login_required = functools.partial(login_required, login_url='admin:login')


def release_column(getter=lambda obj: obj.release, order='release__name'):
    """Return release column function."""
    def release(self):
        """Get release name."""
        release = getter(self)
        return mark_safe(
            '<a href="{url}">{name}</a>'.format(
                url=reverse("admin:core_release_change", args=(release.id,)),
                name=release)) if release else ''
    release.admin_order_field = order
    return release


def normalize_case_title(case_title):
    """Normalize case title."""
    # I'm sick of people adding redundant whitespace to case titles :-)
    case_title = ' '.join(case_title.split())
    # I'm sick of people ending case titles with a dot :-)
    case_title = case_title.rstrip('.')
    return case_title


def find_case_category(case, case_categories):
    """Find case category."""
    default_category = None
    for category in case_categories:
        if set(case['tags']).intersection(frozenset(category['tags'])):
            return category['key']
        if category['default']:
            default_category = category
    return default_category['key'] if default_category else None


def get_release_notes(request, release, case_categories):
    """Get release notes as a string for given release."""
    cases = []
    unmerged_tags = frozenset(tag.strip() for tag in config.TAGS_FOR_UNMERGED_CASES.split(','))
    # Post-process case titles and tags.
    for case_object in release.cases.all():
        case = dict(tags=frozenset(item.tag.name for item in case_object.tagged_items.all()), id=case_object.id)
        # Normalize case titles.
        case['title'] = normalize_case_title(case_object.title)
        if unmerged_tags.intersection(frozenset(case['tags'])):
            case['unmerged'] = True
        # Remove duplicate tags and provide stable sorting.
        case['tags'] = sorted(set(case['tags']))
        cases.append(case)
    # Build up a mapping of (category => [case, ...]) pairs.
    categorized_cases = collections.defaultdict(list)

    for case in cases:
        key = find_case_category(case, case_categories)
        categorized_cases[key].append(case)
    logger.debug("Categorized cases:\n%s", pprint.pformat(dict(categorized_cases)))
    categories = []
    for category in case_categories:
        if category['key'] in categorized_cases and not category['hidden']:
            category['cases'] = [case for case in sorted(categorized_cases[category['key']], key=lambda c: c['id'])]
        categories.append(category)

    return render_to_string('admin/core/release_notes/_single.html', dict(
        release=release, categorized_cases=categorized_cases, categories=categories), RequestContext(request))


def get_case_categories():
    """Get all available case categories."""
    return [
        dict(
            key=category.id,
            hidden=category.is_hidden,
            title=category.title,
            default=category.is_default,
            tags=category.tags.names(),
        ) for category in CaseCategory.objects.all()]


@login_required(login_url='admin:login')
def release_notes(request, release_number, **kwargs):
    """Release notes view."""
    release = get_object_or_404(Release.objects.filter(number=release_number))
    case_categories = get_case_categories()
    return render(request, 'admin/core/release_notes/single.html', dict(
        release=release,
        notes=get_release_notes(request, release, case_categories),
        title=_('Release {number}').format(number=release.number)
    ))


@login_required(login_url='admin:login')
def release_notes_overview(request):
    """Release notes overview view."""
    notes = []
    case_categories = get_case_categories()
    for release in Release.objects.prefetch_related('cases__tagged_items__tag').all().order_by('-number'):
        notes.append((release, get_release_notes(request, release, case_categories)))
    return render(
        request, 'admin/core/release_notes/overview.html', dict(
            categories=(
                category for category in case_categories if not category.is_default and not category.is_hidden),
            notes=notes,
            title=_('Release notes overview')))
