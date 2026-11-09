from tools.progreso.data import aggregate, parse_tsv


def test_parse_and_aggregate():
    header = 'id\ttipo\testado\tdueno\trevisor\tdeps_listas\tdeps\tasignada\tultimo_evento\ttitulo\n'
    rows = parse_tsv(header +
        'T-01\tclaude\tdone\tgpt-dylan:w1\tclaude-elias:r1\tsi\t\t\tevento\tHecha\n' +
        'T-02\tclaude\tclaimed\tcursor-elias:w1\t\tsi\tT-01\t\tevento\tEn curso\n' +
        'T-03\tclaude\topen\t\t\tno\tT-02\tgpt-dylan\t\tBloqueada\n' +
        'T-92\thumano\topen\t\t\tno\tT-02\t\t\tHumana\n')
    stats = aggregate(rows)
    assert stats['percent'] == 100 / 3
    assert stats['states'] == {'done': 1, 'claimed': 1, 'open': 1}
    assert [r['id'] for r in stats['blocked']] == ['T-03']
    assert [r['id'] for r in stats['human']] == ['T-92']
    activity = {r['sesion']: r for r in stats['activity']}
    assert activity['gpt-dylan']['hechas'] == 1
    assert activity['cursor-elias']['en_curso'] == 1
    assert activity['claude-elias']['revisadas'] == 1
    assert aggregate([])['percent'] == 0
