import assert from 'node:assert/strict'
import test from 'node:test'
import {
  combineRemito,
  normalizeRemitoPart,
} from '../src/services/tripRemito.js'

test('normalizeRemitoPart removes punctuation and pads with zeros', () => {
  assert.equal(normalizeRemitoPart('0028.61', 7), '0002861')
  assert.equal(normalizeRemitoPart(' 2,5 ', 3), '025')
  assert.equal(normalizeRemitoPart('001-234', 7), '0001234')
})

test('combineRemito builds provider remito from sanitized parts', () => {
  assert.equal(combineRemito('002', '001', '0028.61'), '002-001-0002861')
  assert.equal(combineRemito('', '', ''), '')
})
