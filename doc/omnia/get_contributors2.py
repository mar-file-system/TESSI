#! /usr/bin/env python3

import requests
import json

# Define your credentials and repository details
owner = 'dell'
repo = 'omnia'
token = '42140bf9b2c0257503fb42be5bd3c81d492ad55b'

# Set up the headers for your requests
headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

def get_contributors():
    url = f'https://api.github.com/repos/{owner}/{repo}/contributors'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f'Failed to retrieve contributors: {response.content}')
        return None

def get_orgs(username):
    url = f'https://api.github.com/users/{username}/orgs'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        orgs = response.json()
        return ', '.join([org['login'] for org in orgs]) if orgs else 'N/A'
    else:
        print(f'Failed to retrieve organizations for {username}: {response.content}')
        return 'N/A'

def main():
    contributors = get_contributors()
    if contributors:
        for contributor in contributors:
            username = contributor['login']
            orgs = get_orgs(username)
            contributions = contributor['contributions']
            print(f'{username} {orgs} {contributions}')

if __name__ == "__main__":
    main()

