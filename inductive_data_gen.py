import argparse
import random
import networkx as nx

def build_graph_from_rdf(rdf_triples):
    G = nx.Graph()
    for h, r, t in rdf_triples:
        G.add_edge(h, t, relation=r)
    return G

def find_gccs(G):
    gccs = list(nx.connected_components(G))
    return gccs

def get_two_hop_neighbors(G, nodes, limit=50):
    extended_nodes = set()
    for node in nodes:
        neighbors = set(nx.single_source_shortest_path_length(G, node, cutoff=2).keys())
        if len(neighbors) > limit:
            neighbors = set(random.sample(neighbors, limit))
        extended_nodes.update(neighbors)
    return list(extended_nodes)

# Function to read RDF triples from a file
def read_rdf_triples(file_path):
    with open(file_path, 'r') as file:
        triples = [line.strip().split() for line in file.readlines()]
    return triples

# Function to write RDF triples to a file
def write_rdf_triples(file_path, triples):
    with open(file_path, 'w') as file:
        for triple in triples:
            file.write(' '.join(triple) + '\n')

# Function to generate inductive datasets
def generate_inductive_datasets(input_file, output_prefix, n_tr, n_inf, p_rel, p_tri):
    # Read the RDF triples from the input file
    rdf_triples = read_rdf_triples(input_file)

    # Step 1: Assume all triples are part of the Giant connected component
    G = rdf_triples

    # Step 2: Randomly split R into R_tr and R_inf
    R = list(set(relation for _, relation, _ in G))
    random.shuffle(R)
    split_index = int(p_rel * len(R))
    R_tr = R[:split_index]
    R_inf = R[split_index:]

    # Step 3: Uniformly sample n_tr entities from V and form V_tr
    V = list(set(entity for triple in G for entity in (triple[0], triple[2])))
    random.shuffle(V)
    V_tr = V[:n_tr]
    V_inf = V[n_tr:n_tr + n_inf]

    # Step 4: Construct E_tr with triples in G that involve entities in V_tr and relations in R_tr
    E_tr = [(h, r, t) for h, r, t in G if h in V_tr and r in R_tr]

    # Steps 5 to 10: As in the original script

    # Step 8: Let G' be the subgraph of G where the entities in V_tr are removed
    G_prime = [(h, r, t) for h, r, t in G if h not in V_tr and t not in V_tr]

    # Step 10: Construct E_inf with triples in G' that involve entities in V_inf and relations in R_inf
    E_inf = [(h, r, t) for h, r, t in G_prime if h in V_inf and r in R_inf]

    # Format the triples for G_tr and G_inf
    rdf_triples_G_tr = ['<{}> <{}> <{}>'.format(h, r, t) for h, r, t in E_tr]
    rdf_triples_G_inf = ['<{}> <{}> <{}>'.format(h, r, t) for h, r, t in E_inf]

    # Output the RDF triples in the requested format
    write_rdf_triples(f'{output_prefix}_tr.txt', rdf_triples_G_tr)
    write_rdf_triples(f'{output_prefix}_inf.txt', rdf_triples_G_inf)

    return f'{output_prefix}_tr.txt', f'{output_prefix}_inf.txt'

# Argument parser for command line interface
def parse_arguments():
    parser = argparse.ArgumentParser(description='Generate Datasets for Inductive Knowledge Graph Completion')
    parser.add_argument('-i', '--input', required=True, help='Input file containing RDF triples')
    parser.add_argument('-o', '--output', required=True, help='Output prefix for the generated datasets')
    return parser.parse_args()

# If this script is run as the main program
if __name__ == '__main__':
    # Parse the command line arguments
    args = parse_arguments()

    # Parameters (example values, these could be arguments as well)
    n_tr = 50  # number of entities to sample for training set
    n_inf = 100 # number of entities to sample for inductive set
    p_rel = 0.5  # probability of selecting a relation for the training set
    p_tri = 0.5  # probability of selecting a triplet for the training set

    # Generate the inductive datasets
    output_tr, output_inf = generate_inductive_datasets(args.input, args.output, n_tr, n_inf, p_rel, p_tri)

    # Print out the names of the generated files
    print(f'Training dataset written to {output_tr}')
    print(f'Inductive dataset written to {output_inf}')