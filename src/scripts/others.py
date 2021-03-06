from collections import defaultdict
import json

from .cli import cli

import click
import cobra as cb
import numpy as np

from sklearn.pipeline import Pipeline
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_selection import f_classif, VarianceThreshold, SelectKBest

from services import DataReader, NamingService, DataWriter
from preprocessing import DynamicPreprocessing, FVARangedMeasurement, PathwayFvaScaler, InverseDictVectorizer
from classifiers import FVADiseaseClassifier
from .optimal_currency_threshold import optimal_currency_threshold


@cli.command()
def threshold_optimization():
    model = cb.io.load_json_model('../dataset/network/recon-model.json')
    print(optimal_currency_threshold(model, (2, 100)))


@cli.command()
def metabolite_by_connected_subsystems():
    model = cb.io.load_json_model('../dataset/network/recon-model.json')
    metabolites = [(len(set([j.subsystem for j in i.reactions])), i.id)
                   for i in model.metabolites]
    print(sorted(metabolites, key=lambda x: x[0], reverse=True))


@cli.command()
def subsystem_statistics():
    categories = DataReader().read_subsystem_categories()
    total = 0
    for k, v in categories.items():
        print(k, len(v))
        total += len(v)
    print('total:', total)


@cli.command()
def fva_range_analysis_save():
    # (X, y) = DataReader().read_data('BC')
    (X, y) = DataReader().read_data('HCC')
    X = NamingService('recon').to(X)
    X = FVARangedMeasurement().fit_transform(X, y)
    with open('../outputs/fva_solutions.txt', 'w') as f:
        for x, label in zip(X, y):
            f.write('%s %s\n' % (label, x))


@cli.command()
def fva_range_with_basic_analysis_save():
    X, y = DataReader().read_data('BC')

    # preproc = DynamicPreprocessing(['naming', 'basic-fold-change-scaler'])
    # X_p = preproc.fit_transform(X, y)
    # import pprint
    # import pdb
    # for i in X_p:
    #     pprint.pprint(i)
    #     pdb.set_trace()

    for x in X:
        for k, v in x.items():
            x[k] = round(v, 3)

    preproc = DynamicPreprocessing(
        ['naming', 'basic-fold-change-scaler', 'fva']).fit(X, y)

    print('model trained...')

    DataWriter('fva_solution_with_basic_fold_change') \
        .write_json_stream(preproc.transform, X)


@cli.command()
def constraint_logging():
    (X, y) = DataReader().read_data('BC')
    X = NamingService('recon').to(X)
    (X_h, y_h) = [(x, l) for x, l in zip(X, y) if l == 'h'][0]
    (X_bc, y_bc) = [(x, l) for x, l in zip(X, y) if l == 'bc'][0]
    FVARangedMeasurement().fit_transform([X_bc, X_h], [y_bc, y_h])


@cli.command()
def border_rate():
    model = DataReader().read_network_model()
    num_border_reaction = len(
        set(r.id for m in model.metabolites for r in m.reactions
            if m.is_border()))
    print(num_border_reaction / len(model.reactions))


@cli.command()
@click.argument('filename')
def fva_min_max_mean(filename):
    (X, y) = DataReader().read_fva_solutions(filename)
    print(fva_solution_distance(X))


@cli.command()
@click.argument('filename')
def fva_diff_range_solutions(filename):
    (X, y) = DataReader().read_fva_solutions(filename)
    X_h = [x for x, l in zip(X, y) if l == 'h']
    X_bc = [x for x, l in zip(X, y) if l == 'bc']
    print(diff_range_solutions(X_h, X_bc))


@cli.command()
@click.argument('top_num_reaction')
def most_correlated_reactions(top_num_reaction):
    (X, y) = DataReader().read_fva_solutions()
    vect = DictVectorizer(sparse=False)
    X = vect.fit_transform(X)
    vt = VarianceThreshold(0.1)
    X = vt.fit_transform(X)
    (F, pval) = f_classif(X, y)

    feature_names = np.array(vect.feature_names_)[vt.get_support()]
    top_n = sorted(
        zip(feature_names, F), key=lambda x: x[1],
        reverse=True)[:int(top_num_reaction)]
    model = DataReader().read_network_model()
    for n, v in top_n:
        print('name:', n[:-4])
        print('reaction:', model.reactions.get_by_id(n[:-4]).reaction)
        print('min-max:', n[-3:])
        print('F:', v)
        print('-' * 10)


@cli.command()
@click.argument('top_num_pathway')
@click.argument('num_of_reactions')
def most_correlated_pathway(top_num_pathway, num_of_reactions):
    (X, y) = DataReader().read_fva_solutions('fva_without.transports.txt')

    vect = [DictVectorizer(sparse=False)] * 3
    vt = VarianceThreshold(0.1)
    skb = SelectKBest(k=int(num_of_reactions))
    X = Pipeline([('vect1', vect[0]), ('vt',
                                       vt), ('inv_vec1', InverseDictVectorizer(
                                           vect[0], vt)), ('vect2', vect[1]),
                  ('skb', skb), ('inv_vec2', InverseDictVectorizer(
                      vect[1], skb)), ('pathway_scoring', PathwayFvaScaler()),
                  ('vect3', vect[2])]).fit_transform(X, y)

    (F, pval) = f_classif(X, y)

    top_n = sorted(
        zip(vect[2].feature_names_, F, pval), key=lambda x: x[1],
        reverse=True)[:int(top_num_pathway)]

    model = DataReader().read_network_model()
    X, y = DataReader().read_data('BC')
    bc = NamingService('recon').to(X)

    subsystem_metabolite = defaultdict(set)
    for r in model.reactions:
        subsystem_metabolite[r.subsystem].update(m.id for m in r.metabolites)

    subsystem_counts = defaultdict(float)
    for sample in bc:
        for s, v in subsystem_metabolite.items():
            subsystem_counts[s] += len(v.intersection(sample.keys()))

    subsystem_counts = {
        i: v / len(subsystem_counts)
        for i, v in subsystem_counts.items()
    }

    for n, v, p in top_n:
        print('name:', n[:-4])
        print('min-max:', n[-3:])
        print('metabolites:%s' % subsystem_counts[n[:-4]])
        print('F:', v)
        print('p:', p)
        print('-' * 10)


@cli.command()
def lasting_anaylsis():
    sample = json.load(open('../dataset/lasting.json'))

    x = DynamicPreprocessing(['fva']).fit_transform(sample, ['bc'])

    import pdb
    pdb.set_trace()
